# Building a corpus

Documents in, cards out, through three human gates.

This is the part that takes real effort. A model does the drafting at every stage, but a person
decides what enters the corpus, three separate times. That is the trade Hive makes: curation is
work, and the system exists to make it cheap enough to sustain rather than to eliminate it.

## Before you start

You need somewhere for the corpus to live. It is a git repository of its own, not this one, laid
out like this:

```
concepts/
  <product>/
    <card>.md
    corrections/
    db/
clients/
  <client>/
    memory/
    issues/
```

`hive-serve` is pointed at `concepts/` and `clients/` at runtime.

You also need a model gateway. Stages 1 and 2 make model calls; nothing else in Hive does. Any
OpenAI-compatible endpoint works. See [configuration](../reference/configuration.md).

## Stage 1: documents to atomic markdown

`hive-prep` converts a pile of source documents into **atomic markdown**: one clean,
single-topic file per source, with metadata frontmatter.

```bash
cd tooling/hive-prep
uv sync --extra dev
```

The commands run in sequence. `hiveprep <command> --help` has the arguments.

| Step | Does |
|---|---|
| `scan` | walk the source tree and write a file inventory CSV with folder-derived hints |
| `dups` | report byte-identical duplicate sets |
| `validate-plan` | check the curation plan is well formed **(review 1)** |
| `dedup-formats` | collapse same-document format variants, such as `X.doc` beside `X.docx`, so each document has one slug |
| `normalize` | convert the plan's includes to PDF intermediates, through LibreOffice |
| `route` | report how many files land in each conversion tier, without using a GPU **(review 2)** |
| `transform` | convert to atomic markdown and strip boilerplate |
| `stamp` | write plan metadata into the frontmatter |
| `validate-atomic` | check every output is well formed: unique slugs, enums, relations |

There are **two things to look at in this stage**, not one. They are numbered here in the order you
meet them; [hive-prep](../reference/hive-prep.md#two-gates) calls the same two its gate 1 and gate
2, and the three whole-system gates counted in [principles](../concepts/principles.md) are review 1
here plus the two in stage 2 below.

### Review 1: the curation plan

`scan` and the curation pass produce a plan file listing every source document with a proposed
decision: include, exclude, duplicate-of, supersedes, plus derived metadata.

**Read it. Edit it. Only then continue.**

This is the highest-leverage twenty minutes in the whole pipeline. The plan is one file. Getting it
wrong means distilling documents you did not want, or missing ones you did, and discovering that
after two model stages have run over them.

The design principle underneath: put the intelligence up front in one reviewable artifact, then let
deterministic code do the rest. Everything after this review is ordinary software operating on an
approved decision, which means it is reproducible and explainable.

### Review 2: the tier tally

`route` is a precheck. It reports how many files will go through each conversion tier - text,
vision, passthrough - and uses no GPU and no model doing it.

**Look at the vision count before running `transform`.** That is the one that costs money, and
`route` exists so the bill is a number you approved rather than one you discovered. A tally far
larger than you expected usually means the plan is including scanned material you did not mean to
keep, which is cheaper to fix in the plan than after conversion.

### Boilerplate stripping

`transform` strips copyright lines, page footers and confidentiality notices using regex rules in
`hiveprep/stripper_rules/`. The product ships one generic set, `default.yaml`.

Vendor-specific rules go in `<product>.yaml` beside it and are **opt-in** via `STRIP_PRODUCT`.
They are corpus-side, and they belong with your corpus rather than here, for a reason worth
understanding: rules tuned to one vendor's footers will happily delete another vendor's prose.

Rules are anchored to footer and header *form*, never to a vendor name alone. In a corpus of one
vendor's manuals, that vendor's name appears in thousands of legitimate sentences.

## Stage 2: atomic markdown to cards

`hive-gen` runs two model passes with a gate after each.

```bash
cd tooling/hive-gen
uv sync --extra dev
```

### Review 3: the taxonomy

Given the documents for one functional area, the model proposes the distinct concepts in them and
which documents cover each. It writes `taxonomy.<area>.draft.yaml` and **stops**.

```bash
CARD_CORPUS_ROOT=/path/to/your/corpus SLICE_AREA=<area> uv run python -m hivegen.run
```

`CARD_CORPUS_ROOT` is your card corpus working tree, and is required: the taxonomy is written there,
not beside the engine. It is a different tree from `hive-prep`'s `CORPUS_ROOT` - that one names the
raw documents going in, this one is the cards coming out.

Review the draft, edit it, save it as `taxonomy.<area>.yaml`.

Getting the concept list right is most of getting the corpus right, and a list of titles is far
cheaper to fix than a directory of distilled prose. Expect to merge concepts that are really one
thing, split ones that are really two, and delete ones that are an artifact of how a document was
organised rather than a real idea.

### Review 4: the drafts

Re-run the same command with an approved taxonomy present. The model now reads each concept's
source documents and writes one card per concept into `drafts/`, each carrying `status: draft`.

Review them. Flip the good ones to `status: approved`.

Card bodies are the substance of the corpus, so this is a genuine read rather than a skim. Watch
for over-summarising: the prompt asks for specifics such as parameters and rules to be preserved,
and a card that has lost them is pleasant to read and useless to work from.

### Promotion

```python
from hivegen.promote import promote
promote("drafts", "concepts", "<product>")
```

Approved drafts move into `concepts/<product>/`. Ids are derived from the resulting paths.

### Post-promote

Three scripts, in order:

```bash
uv run python scripts/product_facet_apply.py concepts/
uv run python scripts/conformance_pass.py concepts/
uv run python scripts/index_generate.py concepts/
```

`product_facet_apply` stamps the product facet. `conformance_pass` normalises frontmatter and
writes the `resource` URL, reading its base from `CARD_BASE_URL`. `index_generate` regenerates
`index.md` at the root and per product.

Then check isolation before you serve anything:

```bash
cd ../hive-serve
CONCEPTS_DIR=/path/to/your/corpus/concepts EVAL_DIR=/path/to/your/corpus/eval \
  uv run python -m hiveserve.run_eval progressive <your-qa-set>
```

`<your-qa-set>` is a bare set name, resolved under `EVAL_DIR`, or a path to a `.jsonl`.

## The corpus profile

Everything Hive needs to know that is true of *your* corpus and false of every other one lives in a
single `corpus-profile.yaml`: the functional areas, the sub-slices, the guide-topic vocabulary, the
product folder aliases, and the facet values the validators gate on.

It ships with the corpus, not with Hive, and is found via `CORPUS_PROFILE`, the working directory,
or beside `ATOMIC_DIR`. `corpus-profile.example.yaml` in the product repository documents every
section and, more usefully, how to get each one wrong.

A missing profile is not an error. It becomes one only when something asks for a vocabulary that
nothing defines, and that error names the setting rather than saying "unknown area".

## Keeping it true

A corpus is not finished when it is built. Cards go stale, and clients turn out to differ from the
general case. That is what [corrections and memory](corrections-and-memory.md) are for.

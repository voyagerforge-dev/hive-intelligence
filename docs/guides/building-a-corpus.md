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

The commands run in sequence:

| Step | Does |
|---|---|
| `scan` | inventory the source tree, hash contents, group duplicates |
| `dups` | report content-identical files across the tree |
| `validate-plan` | check the curation plan is well formed **(gate 1)** |
| `dedup` | drop the duplicates the plan marks |
| `normalize` | clean up whitespace, encodings, structure |
| `route` | decide converter per file, based on format |
| `transform` | convert to markdown and strip boilerplate |
| `stamp` | write metadata frontmatter |
| `validate-atomic` | check every output is well formed |

### Gate 1: the curation plan

`scan` and the curation pass produce a plan file listing every source document with a proposed
decision: include, exclude, duplicate-of, supersedes, plus derived metadata.

**Read it. Edit it. Only then continue.**

This is the highest-leverage twenty minutes in the whole pipeline. The plan is one file. Getting it
wrong means distilling documents you did not want, or missing ones you did, and discovering that
after two model stages have run over them.

The design principle underneath: put the intelligence up front in one reviewable artifact, then let
deterministic code do the rest. Everything after gate 1 is ordinary software operating on an
approved decision, which means it is reproducible and explainable.

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

### Gate 2: the taxonomy

Given the documents for one functional area, the model proposes the distinct concepts in them and
which documents cover each. It writes `taxonomy.<area>.draft.yaml` and **stops**.

```bash
SLICE_AREA=<area> uv run python -m hivegen.run
```

Review it, edit it, save it as `taxonomy.<area>.yaml`.

Getting the concept list right is most of getting the corpus right, and a list of titles is far
cheaper to fix than a directory of distilled prose. Expect to merge concepts that are really one
thing, split ones that are really two, and delete ones that are an artifact of how a document was
organised rather than a real idea.

### Gate 3: the drafts

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
cd ../hive-serve && uv run python -m hiveserve.run_eval progressive <your-qa-set>
```

## A note on functional areas

`hive-gen` slices work by functional area, and the area map lives in `hivegen/load.py` as `AREAS`
and `SUBAREAS`.

**This is currently source code, not configuration**, and the shipped map describes the corpus Hive
was first built against. Pointing Hive at a different body of documents means editing that map.
Making it configuration is tracked work; see
[known limitations](../concepts/principles.md#known-limitations). The same applies to the
guide-topic vocabulary in `hivegen/retopic.py`.

## Keeping it true

A corpus is not finished when it is built. Cards go stale, and clients turn out to differ from the
general case. That is what [corrections and memory](corrections-and-memory.md) are for.

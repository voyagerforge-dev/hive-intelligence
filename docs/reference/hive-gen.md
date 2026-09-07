# hive-gen

Atomic markdown to concept cards. Package `hivegen`, distribution `vf-hive-gen`. The pipeline runner
has no console script: run it as `python -m hivegen.run`. The distribution does ship the eight
`hivegen-*` card commands - see [Scripts](#scripts).

Also hosts the card model, corrections and memory serialisation, and the post-promote scripts.

Narrative version: [building a corpus](../guides/building-a-corpus.md).

## The flow

```
load area  ──►  taxonomy  ──►  ⟨gate: edit and save the taxonomy⟩
                                      │
                                      ▼
                            assign  ──►  distill  ──►  drafts/
                                                          │
                                      ⟨gate: flip status to approved⟩
                                                          │
                                                          ▼
                                                     promote()  ──►  concepts/<product>/
```

```bash
CARD_CORPUS_ROOT=/path/to/your/corpus SLICE_AREA=<area> uv run python -m hivegen.run
```

`CARD_CORPUS_ROOT` is the card corpus working tree, and is required. The taxonomies, `drafts/` and
`.pipeline/` are read and written there. It is **not** hive-prep's `CORPUS_ROOT`, which names the raw
documents going in. See [where the corpus is](configuration.md#where-the-corpus-is) for why it is not
derived and why the two are named apart.

The documents come from `ATOMIC_DIR`, or from R2 when it is empty. It is optional, so it is
validated only when set - but a run that loads **no documents** refuses either way, naming the
source and the filter that produced zero. That is not fussiness: gate 1 hands the inventory to a
prompt asking for 25-45 concepts, so an empty one makes the model invent a taxonomy and
`write_taxonomy` persists the invention into the corpus as though it had been derived.

If no `taxonomy.<area>.yaml` exists **there**, the run proposes one to
`taxonomy.<area>.draft.yaml` and stops. Edit it, save it under the non-draft name, and run again to
get drafts. Both gates print the full path they read and wrote, because a taxonomy proposed while an
approved one sits in a directory nobody looked at is the one failure a bare filename cannot show
you.

Draft generation is **idempotent** (an existing draft is never overwritten) and **per-concept fault
tolerant** (a failure on one concept is reported and skipped rather than killing the run).

## Modules

| Module | Purpose |
|---|---|
| `load.py` | read atomic markdown, slice the corpus into one functional area |
| `taxonomy.py` | propose a concept taxonomy for an area; read and write it as YAML |
| `assign.py` | classify each document into exactly one concept, or exclude it |
| `card.py` | distil a concept's documents into one card |
| `promote.py` | validate approved drafts and move them into the corpus |
| `facets.py` | facet helpers: read, idempotent stamp, cross-facet lint, version derivation |
| `classify_regime.py` | propose a regime facet, human-gated, failing safe to `none` |
| `retopic.py` | re-topic a generic bucket into a controlled guide-topic vocabulary |
| `corrections.py` | record and card serialisation for corrections |
| `memory.py` | record and card serialisation for client memory |
| `run.py` | orchestrate the gate-aware pipeline |
| `llm.py` | OpenAI-compatible chat client with defensive JSON extraction |
| `config.py` | typed settings |
| `profile.py` | the corpus profile: a corpus's domain vocabulary as data rather than as code |
| `corpus.py` | `require_dir`: refuse a configured corpus path that is unset or not a directory, naming the setting. Shared with `hive-serve` |
| `scripts/` | the installed `hivegen-*` commands, each a thin `main()` over the modules above - see [Scripts](#scripts) |

## Slicing

One taxonomy call spanning a whole corpus produces a bad taxonomy, so work is sliced by **functional
area** and each run gets its own.

Areas filter on the `topic:` frontmatter the curation stage assigned. Sub-areas carve oversized
single-topic areas into disjoint keyword families: a document matches when its topic is in the
family's set, its filename contains one of the include keywords, and none of the excludes. A
remainder slice with no includes sweeps whatever the named families did not claim.

> **`AREAS` and `SUBAREAS` are source code, not configuration.** They live in `load.py` and describe
> the corpus Hive was first built against. Pointing Hive at different documents means editing that
> file, and the same is true of the guide-topic vocabulary in `retopic.py`. Making both
> configuration is tracked work; see
> [known limitations](../concepts/principles.md#known-limitations).

## The three gates

**Taxonomy.** The highest-leverage gate in the system. Getting the concept list right is most of
getting the corpus right, and a list of titles is far cheaper to fix than a directory of distilled
prose. Expect to merge concepts that are really one thing, split ones that are really two, and
delete ones that are an artifact of document structure rather than a real idea.

**Drafts.** Cards land in `drafts/` with `status: draft`. Read them properly. Watch for
over-summarising: the prompt asks for parameters and rules to be preserved, and a card that has lost
them reads well and is useless to work from.

**Promotion.** `promote()` validates frontmatter and cross-links before moving anything. A draft
linking to a concept that does not exist fails rather than promoting a broken edge.

Distillation is constrained to emit `related` ids drawn from the ids present in its input, so the
link graph cannot invent targets.

## Post-promote scripts

In order:

| Step | Does |
|---|---|
| `scripts/product_facet_apply.py` | stamp the product facet |
| `hivegen-conformance-pass` | normalise frontmatter, write `resource`, add `## Related` and `# Citations` |
| `hivegen-index-generate` | regenerate the root and per-product `index.md` |

Optionally `scripts/regime_classify.py` with `scripts/regime_apply.py`, and
`scripts/version_apply.py`.

`hivegen-conformance-pass` reads its URL base from `CARD_BASE_URL`. Cards are portable; the URL they
resolve under is not.

`hivegen-index-generate` writes `okf_version` into the root index. That is **the only place** format
version metadata belongs: a corpus has a format version, not each card.

## Authoring seams

`corrections.py` and `memory.py` are pure serialisation between a record and a card file, with no
I/O and no network. The CLI paths and the issue-form automation share them, so a card authored
either way is byte-identical.

`hivegen-memory-conflict-score` and `hivegen-pr-conflict-gate` score a submission against
existing cards and publish a commit status. Hive ships the check; the scheduler that runs it is
deployment-side. `hivegen.scripts.pr_conflict_gate` is also importable, and a caller with glue of
its own composes `pr_touches_memory`, `score_tree` and `verdict_to_status` directly rather than
shelling out.

`hivegen-pr-conflict-gate` decides what to score by matching `--changed-file` values against
`clients_dir`, so the two must share a base: **run it from the directory the changed paths are
relative to** - the repository root, for `git diff --name-only` output - and give `clients_dir` as a
path under it. `clients_dir` must name the clients tree itself, not the directory the gate runs from.
A corpus below the root is matched at its own prefix rather than at `clients/`, while a `clients_dir`
outside the working directory, or equal to it, is refused rather than answered, because a gate that
matches nothing posts green over a memory change nothing scored. Beneath those three the same
refusal catches a `clients_dir` that is simply the wrong tree: **a changed memory card that is
still in the tree, while `clients_dir` holds no memory card at all, is refused**, since the two
disagree about where memory lives and no verdict could be about anything. That is the
contradiction rather than a heuristic. A changeset whose memory cards are all *gone* from the tree
is a deletion instead, and succeeds: there is no new claim left for anything to contradict. Cards
that exist but share no subject are the ordinary healthy outcome and also print `state: success`.
A run with no `--changed-file` at all, and a run with no gateway configured, are refused for the
same reason. `hivegen-memory-conflict-score` is the advisory sibling: with no gateway it prints
the candidate pairs and does not fail the step, and with one it exits non-zero only on a blocking
conflict.

## The model client

`ChatLLM` is a Protocol, so tests inject fakes and no test touches a network.

`extract_json` strips `<think>...</think>` blocks before parsing. Reasoning models wrap
chain-of-thought whose prose contains braces, and parsing that as JSON produces confident nonsense.
It then takes a fenced JSON block, or the first `{` to last `}` span, returning `None` on any
failure.

`BifrostChat.complete` posts an OpenAI-compatible request at temperature 0 and retries transient
errors with linear backoff, returning `None` on final failure. **Callers treat `None` as a hard
failure**, so a network blip never masquerades as a model decision.

## Internals

Module-level detail, verified against the code on 2026-07-30.

### `load.py`

Reads atomic markdown into a source-agnostic `Doc {id, name, text}`, so the rest of the package
does not know or care where documents came from. `load_area_local` and `load_subarea_local` apply
the slice filter from the corpus profile; `load_docs_local` with no filter takes everything.

### `taxonomy.py`, `assign.py`, `card.py`

`taxonomy` proposes a per-area concept list. `assign` classifies each document into exactly one
concept id or `exclude`, so a document cannot inflate two cards with the same content.

`card` distils a concept plus its assigned documents into `{title, description, tags, related,
body}`. Two constraints are enforced in code rather than trusted to the prompt:

- The valid `related` ids are **listed in the prompt**, and
- the response is **filtered against that set** on the way out.

That double enforcement is why cross-links are not hallucinated. A prompt instruction alone would
be followed most of the time, and the failures would be plausible-looking ids that resolve to
nothing.

### `promote.py`

The gate-3 mechanism, and it refuses more than it accepts:

| Refuses | Why |
|---|---|
| `status` is not `approved` | drafts are not knowledge |
| a card already exists at the target path | promotion never overwrites |
| any `related:` id does not resolve | a dangling edge is a broken graph |
| required frontmatter missing | the card cannot be indexed |

It returns `(promoted, invalid)` rather than raising, so one bad draft does not block a batch. The
last three land in `invalid` with their reason; a draft that is not `approved` is passed over
silently, named in neither list.

### `llm.py`

`BifrostChat` is an OpenAI-compatible client with bounded retry and a `User-Agent` it sets on every
request, which is what makes per-stage cost and quality separable in whatever observability the
deployment runs.

`extract_json` strips `<think>…</think>` blocks before parsing. **Reasoning models wrap
chain-of-thought in those tags**, and the JSON that follows is unparseable without removing them
first. Without this, a model switch looks like a total pipeline failure.

### `facets.py`, `classify_regime.py`, `retopic.py`

`facets` stamps and reads `product`, `platform`, `version` and `regime` **idempotently**, and lints
across facets. `classify_regime` is the model-backed proposer, human-gated and fail-safe.
`retopic` re-maps concepts across a taxonomy revision, so an area can be re-sliced without a full
re-distillation.

### `corrections.py`, `memory.py`

Each is a **pure `record ⇄ card` serialization seam** with no I/O, shared by three callers: the
CLI scripts, the issue-to-card workflows, and `hive-author`.

That is the point of them. Three authoring paths that built cards independently would drift, and
the drift would show up as cards that lint differently depending on how they were filed.

## Scripts

The post-promote and authoring tools. All the post-promote ones are **idempotent and LLM-free**, so
re-running over a whole corpus is safe and leaves conformant cards untouched.

**Installed commands.** These ship in the wheel as `[project.scripts]` console scripts, so a
consumer that pins `vf-hive-gen` gets them without reading a file off a host. They live in
`hivegen/scripts/` and each is a thin `main()` over the library. Every one of them puts its corpus
argument through `corpus.require_dir` first, so an unset, empty or absent directory is refused
naming that argument rather than globbed over from the working directory - `hivegen-conformance-pass`
rewrites cards in place, so it refuses before it writes anything.

| Command | Job |
|---|---|
| `hivegen-conformance-pass` | set `resource`, add `timestamp`, regenerate `## Related` and `# Citations` |
| `hivegen-index-generate` | write the root and per-product `index.md` |
| `hivegen-correction-from-issue` / `hivegen-memory-from-issue` | parse an issue-form body into a card |
| `hivegen-corrections-lint` / `hivegen-memory-lint` | structural lint, plus same-client conflict candidates |
| `hivegen-memory-conflict-score` | the model conflict judge, **fail-safe: any error scores as a conflict** |
| `hivegen-pr-conflict-gate` | turn the conflict verdict into a commit-status payload |

They arrived at 0.7.0. Before that the wheel carried `packages = ["hivegen"]` and nothing else, so
they were installable at no version and a consumer read them from a checkout somebody had seeded by
hand. From 0.7.0 these commands are the only supported entry point: the old
`tooling/hive-gen/scripts/` paths for them are gone, and a caller still reading one switches to the
command.

**Still in-tree only**, under `tooling/hive-gen/scripts/`, because they are corpus-build tools a
maintainer runs from a checkout rather than a consumer's command line:

| Script | Job |
|---|---|
| `product_facet_apply.py` | stamp `product`, `platform`, `version` for one product |
| `version_apply.py` | derive `version` from source-reference years |
| `regime_classify.py` / `regime_apply.py` | propose (model) then apply (deterministic) the regime facet |
| `new_correction.py` / `new_memory.py` | scaffold a draft card from the CLI |
| `run_pipeline.sh` | detached distillation run, logging to `.pipeline/` |

The issue-parsing commands are **path-traversal guarded**: the product is checked against an
allowlist and a client id must match `\A[a-z0-9-]+\Z`. They parse attacker-influenceable text
(an issue body) into a filesystem path, so this is load-bearing rather than defensive decoration.

## Tests

Fakes only; the model client is injected, so nothing in the suite makes a network call. A few
assertions need the card-submission surface that ships with a corpus and skip with a stated reason
without it. Use `uv run pytest --collect-only -q` in `tooling/hive-gen/` for the current inventory
rather than a count written down here.

## Configuration

See [configuration](configuration.md#hive-gen).

## Gotchas

**The taxonomy file name is the gate.** The run writes `taxonomy.<area>.draft.yaml` and reads
`taxonomy.<area>.yaml`. Leaving the draft suffix in place means the gate never opens and the run
keeps proposing.

**`BIFROST_TIMEOUT_S` defaults to 300 for a reason.** Reasoning models can be slow, and a short
timeout makes every retry time out too, turning a slow run into zero results.

**`MAX_CHARS` truncates source input per distillation call.** A concept with more source material
than the budget is distilled from a prefix, silently. Split the concept rather than raising it.

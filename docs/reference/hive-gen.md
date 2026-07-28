# hive-gen

Atomic markdown to concept cards. Package `hivegen`, distribution `vf-hive-gen`. No console script:
run it as `python -m hivegen.run`.

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
SLICE_AREA=<area> uv run python -m hivegen.run
```

If no `taxonomy.<area>.yaml` exists, the run proposes one to `taxonomy.<area>.draft.yaml` and stops.
Edit it, save it under the non-draft name, and run again to get drafts.

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

In order, from `scripts/`:

| Script | Does |
|---|---|
| `product_facet_apply.py` | stamp the product facet |
| `conformance_pass.py` | normalise frontmatter, write `resource`, add `## Related` and `# Citations` |
| `index_generate.py` | regenerate the root and per-product `index.md` |

Optionally `regime_classify.py` with `regime_apply.py`, and `version_apply.py`.

`conformance_pass` reads its URL base from `CARD_BASE_URL`. Cards are portable; the URL they resolve
under is not.

`index_generate` writes `okf_version` into the root index. That is **the only place** format version
metadata belongs: a corpus has a format version, not each card.

## Authoring seams

`corrections.py` and `memory.py` are pure serialisation between a record and a card file, with no
I/O and no network. The CLI paths and the issue-form automation share them, so a card authored
either way is byte-identical.

`scripts/memory_conflict_score.py` and `scripts/pr_conflict_gate.py` score a submission against
existing cards and publish a commit status. Hive ships the check; the scheduler that runs it is
deployment-side.

## The model client

`ChatLLM` is a Protocol, so tests inject fakes and no test touches a network.

`extract_json` strips `<think>...</think>` blocks before parsing. Reasoning models wrap
chain-of-thought whose prose contains braces, and parsing that as JSON produces confident nonsense.
It then takes a fenced JSON block, or the first `{` to last `}` span, returning `None` on any
failure.

`BifrostChat.complete` posts an OpenAI-compatible request at temperature 0 and retries transient
errors with linear backoff, returning `None` on final failure. **Callers treat `None` as a hard
failure**, so a network blip never masquerades as a model decision.

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

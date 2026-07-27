# OKF tooling - hive-gen (`hivegen`)

*Stage 2 of the OKF pipeline: distills atomic markdown into cross-linked concept cards, and hosts the post-promote + corrections/memory authoring scripts. Conceptual model in [architecture/pipeline.md §4](../architecture/pipeline.md#4-stage-2-card-creation-hivegen).*

**Tooling reference:** [Hub](README.md) · [hive-prep](hive-prep.md) · **hive-gen** · [hive-serve](hive-serve.md) · [hive-dbparse](hive-dbparse.md) · [hive-author](hive-author.md) · [hive-zendesk](hive-zendesk.md) · [Architecture & Concepts](../architecture/pipeline.md)

`hivegen` (distribution `vf-hive-gen`, import `hivegen`) turns the curated WMOS atomic-markdown corpus into OKF concept cards through a 3-gate, human-in-the-loop LLM flow: propose a per-area concept **taxonomy** (Gate 1), **assign** each doc to one concept, **distill** each concept's docs into a draft card (Gate 2), then **promote** approved drafts into `concepts/<product>/` with frontmatter and cross-link validation (Gate 3). All LLM calls go through the firm's Bifrost gateway (OpenAI-compatible, key `VK_OKF`): `minimax-m3` for taxonomy and distill, `deepseek-v4-flash` for assign. After promotion, a set of deterministic post-promote scripts stamp product/platform/version/regime facets, run an OKF-conformance pass (resource URIs, `## Related`, `# Citations`), and regenerate the index hierarchy. The package also hosts the corrections and client-memory authoring seams (CLI + GitHub Issue-Form actions) and the memory-conflict PR gate that runs under Windmill.

## Module index
| Module | Purpose |
|---|---|
| `load.py` | Read atomic markdown and slice the corpus into one generatable functional area/sub-area. |
| `taxonomy.py` | LLM-propose a fine-grained concept taxonomy for an area; read/write it as YAML (Gate 1). |
| `assign.py` | Classify each doc into exactly one taxonomy concept or `exclude` (LLM). |
| `card.py` | Distill a concept's source docs into one OKF card (frontmatter + curated prose). |
| `promote.py` | Validate approved drafts (frontmatter + cross-links) and move them into the bundle (Gate 3). |
| `facets.py` | Pure facet helpers: read frontmatter, idempotent stamp, cross-facet edge lint, version derivation. |
| `classify_regime.py` | LLM proposer for the OPS/traditional regime either-or (human-gated, fail-safe to `none`). |
| `retopic.py` | Re-topic the generic "WMS reference doc" bucket into controlled guide-topics (LLM, dry-run default). |
| `corrections.py` | Pure record⇄card serialization for correction cards. |
| `memory.py` | Pure record⇄card serialization for client-memory cards. |
| `run.py` | Orchestrate the gate-aware pipeline (taxonomy → assign → distill) + detached entrypoint. |
| `llm.py` | Bifrost (OpenAI-compatible) chat client + defensive JSON extraction. |
| `config.py` | Typed pydantic settings (env / `.env`): source dir, slice, Bifrost creds, model names. |

## Modules

### `load.py`
**Purpose.** Read WMS atomic markdown and slice the ~1,239-doc corpus into one coherent functional area (or keyword sub-area) so each `hivegen` run gets its own taxonomy instead of one taxonomy call spanning the whole corpus.
**Key logic.** Two slice mechanisms. Legacy: `is_wave_replen(name)` filename-keyword match (the original Wave/Replenishment slice). Preferred: filter on the curator-assigned `topic:` frontmatter. `AREAS` maps ~50 area names to the exact `topic:` values the curator wrote (inbound, outbound, oSCI/Slotting/LM areas, re-topiced `Guide:` chapters, etc.). `SUBAREAS` carves the two oversized single-topic areas (`Interfaces` 229 docs, `System Control` 111 docs) into disjoint keyword families via a `SubArea(topics, include, exclude)` dataclass: a doc matches when its `topic:` is in `topics` AND its filename contains an `include` keyword (or `include` is empty) AND none of `exclude`; a remainder slice with empty `include` sweeps whatever the named families did not claim. `frontmatter_topic` parses the YAML frontmatter defensively (returns `""` on any error). `load_docs_local` applies the topic set (case-insensitive) then the `name_include`/`name_exclude` substring filters; `load_area_local`/`load_subarea_local` resolve a name to its docs and raise `KeyError` on an unknown name.
**Inputs → outputs.** Local dir or S3/R2 client + prefix → `list[Doc]` (`Doc(id, name, text)`, frozen dataclass).
**Dependencies.** internal: none (pure). external: `PyYAML`, stdlib `pathlib`. `load_docs` takes an injected `s3` client (boto3 supplied by the caller).
**Invoked / deployed.** Called by `run.main()`; the `AREAS`/`SUBAREAS` tables are the registration point for a new product's areas.

### `taxonomy.py`
**Purpose.** Gate 1 - propose a fine-grained concept taxonomy for a functional area from the doc inventory.
**Key logic.** `propose_taxonomy` builds an inventory string (`- <name>: <first 400 chars>` per doc), sends it with a system prompt that asks for ONLY a JSON object `{"concepts":[{id,title,description,aliases}]}` and instructs roughly 25-45 narrow single-topic concepts (one per distinct process/screen/algorithm/config entity, ~1-4 source docs each), parses via `extract_json`, and coerces each entry into a `Concept` pydantic model (silently skipping malformed entries). `write_taxonomy` dumps to YAML (`sort_keys=False`); `load_taxonomy` reads it back. The proposal is written to `taxonomy.<area>.draft.yaml` for human review; a human saves the approved version as `taxonomy.<area>.yaml`.
**Inputs → outputs.** `list[Doc]` + `ChatLLM` → `list[Concept]`; YAML file ⇄ `list[Concept]`.
**Dependencies.** internal: `hivegen.llm` (`ChatLLM`, `extract_json`), `hivegen.load.Doc`. external: `pydantic`, `PyYAML`.
**Invoked / deployed.** `run.main()` calls it only when no `taxonomy.<area>.yaml` exists, then stops (Gate 1). Backend model `minimax-m3`.

### `assign.py`
**Purpose.** Classify each doc into exactly one approved-taxonomy concept, or `exclude` for instance-specific/junk docs.
**Key logic.** `classify_doc` sends the concept option list plus the doc's first 600 chars and expects ONLY `{"concept_id": "<id-or-exclude>"}`; any id not in `{concept ids} | {"exclude"}` (including an LLM blip that returns `None` from `complete`) falls back to `exclude` - so an unparsed answer never silently invents a concept. `assign_docs` loops all docs into `assignments: {concept_id -> [doc_id]}` plus an `excluded` list.
**Inputs → outputs.** `list[Doc]`, `list[Concept]`, `ChatLLM` → `(assignments, excluded)`.
**Dependencies.** internal: `hivegen.llm`, `hivegen.load.Doc`, `hivegen.taxonomy.Concept`. external: none direct.
**Invoked / deployed.** Called by `run.generate_drafts`; the assignment map is also dumped to `.pipeline/<area>/assignments.yaml`. Backend model `deepseek-v4-flash`.

### `card.py`
**Purpose.** Distill one concept's assigned source docs into a single OKF concept card (YAML frontmatter + reusable prose body).
**Key logic.** `distill_concept` concatenates the source docs (truncated to `max_chars`), and when `related_ids` is supplied appends an explicit "Valid concept ids for the `related` field (choose only from these, or empty)" line. The system prompt asks for ONLY `{title,description,tags,related,body}` and requires `related` to be a subset of the provided ids. On the way out the code **re-filters** `related` to `set(related_ids)` in Python, so a hallucinated cross-link cannot survive even if the LLM ignores the instruction - `related` is always constrained to the real taxonomy. Returns `None` (skip) if there is no parseable JSON or an empty body. `build_okf_card` renders frontmatter + body. The stamped frontmatter fixes `type: concept`, `resource: wmos` (a placeholder upgraded to the served-card URI later by `conformance_pass.py`), `sources` as `{kind: wms-doc, ref: <name>}` per doc, `distilled_at`/`timestamp` = today, and `status: draft`.
**Inputs → outputs.** `Concept`, `list[Doc]`, `ChatLLM`, `max_chars`, `today`, optional `related_ids` → card markdown string or `None`.
**Dependencies.** internal: `hivegen.llm`, `hivegen.load.Doc`, `hivegen.taxonomy.Concept`. external: `PyYAML`.
**Invoked / deployed.** Called per concept by `run.generate_drafts` writing to `drafts/`. Backend model `minimax-m3`.

### `promote.py`
**Purpose.** Gate 3 - validate approved drafts and move them into the served bundle at `concepts/<product>/`.
**Key logic.** `promote` builds the set of `known_ids` from existing `concepts/**/*.md` (product-relative paths, suffix stripped) plus the drafts being promoted (`<product>/<stem>`). For each draft it skips anything whose frontmatter `status` is not `approved`; refuses to overwrite an existing destination card (records it in `invalid`); runs `validate_card`, which checks the `_REQUIRED` frontmatter key set (`type,title,description,tags,resource,sources,related,distilled_at,status`) and that every `related` id resolves to a `known_id`; and only on a clean pass writes the card to `concepts/<product>/` and `unlink`s the draft. Returns `(promoted, invalid)`.
**Inputs → outputs.** `drafts_dir`, `concepts_dir`, `product` → `(promoted names, {name: [errors]})`.
**Dependencies.** internal: none (reads frontmatter with its own `parse_frontmatter`). external: `PyYAML`.
**Invoked / deployed.** Run by hand after the human flips drafts to `status: approved` (see [OKF-Pipeline §9](../architecture/pipeline.md#9-running-it)); no auto-invocation from `run.py`.

### `facets.py`
**Purpose.** Pure, LLM-free helpers over card frontmatter used by every post-promote facet script.
**Key logic.** `_split` divides a card on the `---` fences; `read_facets` parses the frontmatter dict; `card_regime` reads the `regime` value. `stamp_facets` is **idempotent and additive**: it appends `k: v` lines only for keys not already present, so re-running a facet script never rewrites or duplicates an existing facet. `cross_facet_edges` walks every card's `related` links and returns `(src, dst)` pairs where both endpoints have a facet value (default `regime`) and the values differ - the lint that surfaces cross-regime bleed. `derive_versions` extracts release years from `sources[].ref` via the `open-systems-(20\d\d)` regex.
**Inputs → outputs.** card text / card dict → dicts, strings, edge lists.
**Dependencies.** internal: none. external: `PyYAML`, stdlib `re`.
**Invoked / deployed.** Imported by `product_facet_apply.py`, `osci_facet_apply.py`, `version_apply.py`, `regime_apply.py`, and `classify_regime.py`.

### `classify_regime.py`
**Purpose.** LLM proposer that labels one card by order-fulfilment regime - `ops` (OPS / DC Order Planning / Wave-Stream orchestration), `traditional` (standalone replenishment/tasking/wave execution), or `none` (outside the either-or).
**Key logic.** `classify_card_regime` reads the card's title/description/tags plus the first 2000 chars, prompts for ONLY `{label,rationale,confidence}`, and is **fail-safe**: any label not in `{traditional,ops,none}` or an unparsed reply returns `{"label":"none","confidence":0.0}`, and a non-numeric confidence coerces to `0.0`. It only proposes; the label is written to a reviewable YAML and applied by a separate human-gated script.
**Inputs → outputs.** card text + `ChatLLM` → `{label, rationale, confidence}`.
**Dependencies.** internal: `hivegen.facets.read_facets`, `hivegen.llm`. external: none direct.
**Invoked / deployed.** Called by `scripts/regime_classify.py` (backend `assign_model`, i.e. `deepseek-v4-flash`).

### `retopic.py`
**Purpose.** Standalone script/module that re-topics the generic "WMS reference doc" bucket (WMOS guide/manual chapters) into 12 controlled `Guide:` topics that then become `AREAS` keys.
**Key logic.** `newest_docs` keeps one path per guide base-name (year-collapsed, highest `version:` wins). `classify` sends the controlled `TOPICS` vocabulary + title + first 1200 body chars and expects ONLY `{"topic": "<exact topic string>"}`; a topic not in the vocabulary becomes `UNCLASSIFIED`. `set_topic` rewrites the `topic:` frontmatter line in place. Dry-run by default; `--apply` writes (skipping `UNCLASSIFIED`), `--limit N` caps the batch. Prints a topic distribution. Adds `hive-gen/` to `sys.path` so it runs directly.
**Inputs → outputs.** atomic-markdown docs under `sources/wms-atomic/docs` → rewritten `topic:` frontmatter (in place).
**Dependencies.** internal: `hivegen.config.get_settings`, `hivegen.llm.BifrostChat`/`extract_json`. external: stdlib `re`, `pathlib`.
**Invoked / deployed.** `python retopic.py [--apply] [--limit N]` on the dev box (backend `assign_model`). One-off corpus-shaping step feeding `load.AREAS`.

### `corrections.py`
**Purpose.** Pure record⇄card serialization seam for correction cards at `concepts/<product>/corrections/<slug>.md` - the single formatter both the CLI and the GitHub Issue-Form action author through.
**Key logic.** `record_to_correction` builds fixed frontmatter (`type: correction`, `corrects`, `supersedes`, `product`, an empty `resource` placeholder filled later by `conformance_pass.py`, `sources` as `{kind: correction-source, ref}`, `status` default `approved`) and a `## Correction` + `## Rationale` body. `correction_to_record` is the inverse: regex-splits frontmatter/body and pulls each `##` section back out. No I/O, no LLM.
**Inputs → outputs.** record dict ⇄ correction-card markdown.
**Dependencies.** internal: none. external: `PyYAML`, stdlib `re`.
**Invoked / deployed.** Used by `new_correction.py` (CLI) and `correction_from_issue.py` (CI action).

### `memory.py`
**Purpose.** Pure record⇄card serialization seam for client-memory cards at `clients/<client>/memory/<slug>.md`. Mirrors `corrections.py`.
**Key logic.** `record_to_memory` builds `type: memory` frontmatter (`client`, `product`, `platform`, `related`, `supersedes`, `submitted_by`, `resource`, `sources` as `{kind: memory-source, ref}`, `status` default `approved`) and a `## Memory` + `## Context` body. `memory_to_record` is the inverse. No I/O, no LLM.
**Inputs → outputs.** record dict ⇄ memory-card markdown.
**Dependencies.** internal: none. external: `PyYAML`, stdlib `re`.
**Invoked / deployed.** Used by `new_memory.py` (CLI) and `memory_from_issue.py` (CI action).

### `run.py`
**Purpose.** Gate-aware orchestrator that wires load → taxonomy → assign → distill, plus the detached `main()` entrypoint.
**Key logic.** `generate_drafts` runs `assign_docs`, dumps `assignments.yaml` under `.pipeline/<area>/`, and for each concept with assignments calls `distill_concept` (passing all *other* concept ids as `related_ids`), writing `drafts/<concept-id>.md`. It is **idempotent** (never overwrites an existing draft) and per-concept **fault-tolerant** (a distill exception is printed and skipped, not fatal). `main()` resolves the `SLICE_AREA` to an area or sub-area (raising `SystemExit` on an unknown one), computes a per-area taxonomy stem (`taxonomy.<area>` so areas never clobber each other), loads docs from `ATOMIC_DIR` (local, source of truth) or R2 (`boto3` fallback), and enforces the gates: if no `taxonomy.<area>.yaml` exists it proposes one to `.draft.yaml` and **stops at Gate 1**; otherwise it distills drafts and **stops at Gate 2** (human flips `status: approved`, then runs `promote`).
**Inputs → outputs.** `Settings` + filesystem → `taxonomy.<area>.draft.yaml` (Gate 1) or `drafts/*.md` (Gate 2).
**Dependencies.** internal: `assign`, `card`, `llm`, `load`, `taxonomy`, `config`. external: `PyYAML`, optional `boto3`.
**Invoked / deployed.** `python -m hivegen.run` (usually via `run_pipeline.sh`). `main()` is marked `pragma: no cover` (live wiring).

### `llm.py`
**Purpose.** The one Bifrost chat client + defensive JSON extraction shared by every LLM step.
**Key logic.** `ChatLLM` is a `Protocol` (`complete(system, user) -> str | None`) so tests inject fakes. `extract_json` first strips `<think>...</think>` blocks - reasoning models like `minimax-m3` wrap chain-of-thought whose prose can contain braces - then pulls a JSON object from a ```` ```json ```` fence or the first `{`..last `}` span, returning `None` on any decode failure or non-dict. `BifrostChat.complete` POSTs an OpenAI-compatible `/chat/completions` request (`temperature: 0`, bearer `VK_OKF`, `User-Agent: hivegen/0.1` for the Langfuse UA-slice) and retries transient `HTTPError`/`KeyError`/`IndexError` up to `retries` times with linear backoff, returning `None` on final failure - callers treat `None` as a hard failure so a blip never masquerades as a decision.
**Inputs → outputs.** system+user strings → raw content string or `None`; raw string → dict or `None`.
**Dependencies.** internal: none. external: `httpx`, stdlib `json`/`re`/`time`.
**Invoked / deployed.** Every LLM-touching module and script; a fresh `BifrostChat` is constructed per model in `run.main()` and the regime/retopic scripts.

### `config.py`
**Purpose.** Typed, env/`.env`-backed settings (`pydantic-settings`) for the whole pipeline.
**Key logic.** `Settings` fields: `atomic_dir` (local source of truth; when set, R2 is not read), `slice_area` (which `AREAS`/`SUBAREAS` slice), R2 creds/prefix (fallback reader), required `bifrost_base` + `bifrost_api_key`, model names defaulting to `taxonomy_model=minimax-m3`, `assign_model=deepseek-v4-flash`, `distill_model=minimax-m3`, `max_chars=24000`, and `bifrost_timeout_s=300` (deliberately > 150s because `minimax-m3` reasoning can be slow - too-short a timeout makes every retry time out to zero results). `get_settings` is `lru_cache`d.
**Inputs → outputs.** environment / `.env` → `Settings`.
**Dependencies.** external: `pydantic-settings`.
**Invoked / deployed.** `run.main()`, `regime_classify.py`, `retopic.py`.

## Scripts (`scripts/`)

### Facet / conformance / index scripts (post-promote, deterministic)
These run over `concepts/` after each distillation. All are LLM-free (except regime classification) and rely on `facets.stamp_facets`, so they are idempotent.

### `product_facet_apply.py`
**Purpose.** Stamp `product`/`platform` (caller-supplied) and `version` on promoted cards. Generalizes `osci_facet_apply.py`. **Key logic.** For every `concepts/**/*.md` (skipping `index.md`), `version` = sorted union of each source doc's `version:` frontmatter read from the atomic dir; `product`/`platform` are uniform. Idempotent stamp. **Inputs → outputs.** `<concepts_dir> <atomic_dir> <product> <platform>` → in-place facets. **Invoked / deployed.** Dev-box CLI, the standard post-promote facet step for any product.

### `osci_facet_apply.py`
**Purpose.** The oSCI-specific predecessor: hardcodes `product=osci`, `platform=open-systems`. **Key logic.** Same version-union logic, single-level `concepts/*.md` glob. **Inputs → outputs.** `<concepts_dir> <atomic_dir>`. **Invoked / deployed.** Dev-box CLI (superseded by `product_facet_apply.py` for new products).

### `version_apply.py`
**Purpose.** Stamp only `version` from source-ref release years (`facets.derive_versions`). **Key logic.** Version-neutral cards (no year in sources) are left untouched; prints a stamp-count distribution (0=neutral, 1=single, 2+=multi-release). **Inputs → outputs.** `<concepts_dir>` → in-place `version`. **Invoked / deployed.** Dev-box CLI.

### `regime_classify.py`
**Purpose.** LLM-classify every card by regime into a reviewable `regime-classification.yaml`. **Key logic.** Wraps `classify_card_regime` (backend `assign_model`), records `{id,label,rationale,confidence}` plus `needs_review = label != none and confidence < 0.75` to flag low-confidence proposals for the human. **Inputs → outputs.** `<concepts_dir> <out.yaml>`. **Invoked / deployed.** Dev-box CLI; proposer only - never writes to cards.

### `regime_apply.py`
**Purpose.** Apply an approved `regime-classification.yaml`: stamp `regime` on `ops`/`traditional` cards, uniform `product: wms`/`platform: wmos` on all, then report remaining cross-regime `related` edges. **Key logic.** Only participant labels get a `regime` facet (`none` is left neutral); after stamping it runs `facets.cross_facet_edges` and prints `FIX: src -> dst` for any cross-regime bleed to resolve by hand. **Inputs → outputs.** `<concepts_dir> <regime-classification.yaml>` → in-place facets + edge report. **Invoked / deployed.** Dev-box CLI, human-gated (runs only after the classification YAML is reviewed).

### `conformance_pass.py`
**Purpose.** One-time (idempotent) OKF-conformance pass over the bundle. **Key logic.** Per card: sets `resource` to `https://hive.example.com/card/<cid>` and inserts `timestamp` after `distilled_at` if absent; strips any previously generated sections then appends a `## Related` section (bundle-relative markdown links from the `related` frontmatter, using a title map) and a `# Citations` section (numbered `sources[].ref`). Existing frontmatter keys are preserved; `index.md`/`log.md` skipped. **Inputs → outputs.** `<concepts_dir>` → in-place cards. **Invoked / deployed.** Dev-box CLI, run after facet-apply and before index-generate.

### `index_generate.py`
**Purpose.** Regenerate the OKF index hierarchy (progressive disclosure). **Key logic.** Writes `<product>/index.md` (no frontmatter, concept links sorted by title with descriptions; corrections excluded) and a root `index.md` (the one place `okf_version: "0.1"` frontmatter is allowed) listing each product by descending concept count. `PRODUCT_NAMES` maps slugs to display names. **Inputs → outputs.** `<concepts_dir>` → `index.md` files. **Invoked / deployed.** Dev-box CLI, final post-promote step.

### Correction authoring scripts
Both author through `hivegen.corrections.record_to_correction`.

### `new_correction.py`
**Purpose.** Scaffold a placeholder correction card to fill in and PR. **Key logic.** Builds a `status: draft` record with `<...>` placeholders, slugs the title, writes to `concepts/<product>/corrections/<slug>.md`. **Inputs → outputs.** `<product> <target-concept-id> "<title>" [concepts_dir]`. **Invoked / deployed.** Dev-box CLI.

### `correction_from_issue.py`
**Purpose.** Turn a Correction Issue-Form body into an `approved` correction card. Called by `.github/workflows/correction-from-issue.yml`. **Key logic.** `parse_issue` extracts `###`-heading fields (treating `_No response_` as empty); `validate_record` is a **path-safety gate** - `corrects` must be `<product>/<concept>`, `product` must be in `ALLOWED_PRODUCTS`, and no `..`/absolute segments - raising `SystemExit` on any unsafe value so a malicious issue cannot escape `concepts/<product>/corrections/`. **Inputs → outputs.** `<issue_body_file> <concepts_dir>` → prints card path. **Invoked / deployed.** CI (GitHub Action).

### `corrections_lint.py`
**Purpose.** Lint correction cards. **Key logic.** Errors (exit 1): dangling `corrects` target (missing or itself a correction), `supersedes` an unknown correction, or an approved card that has been superseded by an active correction but is still `approved`. Warning (non-fatal): more than one live active correction on one concept (potential conflict). **Inputs → outputs.** `<concepts_dir>` → stdout + exit code. **Invoked / deployed.** CI / dev-box CLI.

### Memory authoring scripts
Both author through `hivegen.memory.record_to_memory`.

### `new_memory.py`
**Purpose.** Scaffold a placeholder client-memory card. **Key logic.** `status: draft` record with `<...>` placeholders → `clients/<client>/memory/<slug>.md`. **Inputs → outputs.** `<client> <product> "<title>" [clients_dir]`. **Invoked / deployed.** Dev-box CLI.

### `memory_from_issue.py`
**Purpose.** Turn a Memory Issue-Form body into an `approved` memory card. Called by `.github/workflows/memory-from-issue.yml`. **Key logic.** Parses `###` fields, sets `submitted_by` from `ISSUE_AUTHOR` env and `resource` to the served URI; `validate_record` gates `product` against `ALLOWED_PRODUCTS` and `client` against `\A[a-z0-9-]+\Z` (the `\A..\Z` anchors reject a trailing newline, and `..`/empty are rejected) to prevent path traversal. **Inputs → outputs.** `<issue_body_file> <clients_dir>` → prints card path. **Invoked / deployed.** CI (GitHub Action).

### `memory_lint.py`
**Purpose.** Lint memory cards and emit conflict CANDIDATES for the LLM scorer. **Key logic.** Structural errors (exit 1): bad/missing product, dangling `related` concept target, `supersedes` an unknown or different-client memory, or a superseded-but-still-approved card. It then generates conflict **candidates** - pairs of active same-client memories that share a `related` id or `tag` - which do NOT fail the lint; they are handed to the conflict scorer. **Inputs → outputs.** `<clients_dir> <concepts_dir>` → errors + candidate pairs. **Invoked / deployed.** CI / dev-box; also imported by the conflict gate.

### `memory_conflict_score.py`
**Purpose.** LLM conflict-probability gate over `memory_lint`'s candidate pairs (authoring/CI-side only - never the serving connector). **Key logic.** `score_pair` asks an injected `ChatLLM` whether two same-client memories make mutually incompatible claims (overlap is not conflict; only contradiction), expecting `{probability, rationale}`. It is **fail-safe-to-block**: any LLM error, unparseable reply, or non-numeric probability scores `1.0`, so an LLM outage blocks rather than waves through. `gate` classifies pairs by threshold (`>=0.6` block, `>=0.3` review). The `__main__` path re-runs `memory_lint`, and if no `BIFROST_*` env is set it degrades to advisory-only (exit 0). **Inputs → outputs.** candidate pairs + memories + LLM → `(blocking, review)`; exit 1 if blocking. **Invoked / deployed.** CI / dev-box (backend `CONFLICT_MODEL`, default `minimax-m3`); composed by `pr_conflict_gate.py`.

### `pr_conflict_gate.py`
**Purpose.** Orchestration core for the memory-conflict PR gate, run by the Windmill runnable `f/example/okf/memory_conflict_gate`. **Key logic.** Pure/testable - the LLM and all I/O are injected by the caller. `pr_touches_memory` short-circuits PRs that do not touch `knowledge/okf/clients/**/memory/*.md`. `score_tree` composes `memory_lint.lint` + `memory_conflict_score.gate` over a checked-out PR tree. `verdict_to_status` turns the verdict into a GitHub commit-status payload for context `okf/memory-conflict` (`failure` on any blocking OR review pair, else `success`, descriptions truncated to 140 chars). This is the required check enforced on `main` branch protection. **Inputs → outputs.** changed-files / tree + LLM → commit-status dict. **Invoked / deployed.** The Windmill runnable `f/example/okf/memory_conflict_gate` (verify); `okf/memory-conflict` is a required status check on `main` branch protection.

### `run_pipeline.sh`
**Purpose.** Detached pipeline launcher (does not babysit). **Key logic.** `cd`s to the package, `mkdir`s the repo `.pipeline/`, and `setsid uv run python -m hivegen.run` backgrounded with output to a timestamped `.pipeline/run-*.log`; prints the tail command. **Invoked / deployed.** Dev-box (`bash scripts/run_pipeline.sh`).

## Deployment & runtime
`hivegen` runs on the dev box via `uv`; there is no `deploy/` dir and no long-running service. The typical flow (see [OKF-Pipeline §9](../architecture/pipeline.md#9-running-it)): `cd tooling/hive-gen && uv sync --extra dev`, set `ATOMIC_DIR` and the Bifrost `VK_OKF` credentials in `.env`, then run per area with `SLICE_AREA=<area> python -m hivegen.run` - Gate 1 writes `taxonomy.<area>.draft.yaml` and stops; a human reviews and saves `taxonomy.<area>.yaml`; re-running writes `drafts/`; the human flips `status: approved` and calls `promote(drafts, concepts, <product>)` (Gate 3). The post-promote scripts then run over `concepts/` in order: `product_facet_apply.py` → `conformance_pass.py` → `index_generate.py` (with `regime_classify.py`/`regime_apply.py` and `version_apply.py` as needed). Bifrost is the sole LLM gateway (OpenAI-compatible, key `VK_OKF` sourced from SOPS (verify); `bifrost_base`/`bifrost_api_key` required, `bifrost_timeout_s=300`); calls carry `User-Agent: hivegen/0.1` for the Langfuse UA-slice. The corrections/memory Issue-Form scripts run in GitHub Actions; `pr_conflict_gate.py` runs under whatever scheduler your deployment uses, publishing a commit status that can be made a required check on `main`.

## Tests
Fakes-only, no network: `ChatLLM` is a `Protocol`, so every test injects a fake LLM and drives the filesystem in `tmp_path` (`respx` is available for `BifrostChat` HTTP-level tests). Run with `cd tooling/hive-gen && uv run pytest -q` (`uv sync --extra dev` first). 24 test modules cover the package (one per core module plus each script seam): `test_load`, `test_taxonomy`, `test_assign`, `test_card`, `test_promote`, `test_facets`, `test_classify_regime`, `test_corrections`, `test_memory`, `test_run`, `test_llm`, `test_config`, and the script tests `test_product_facet_apply`, `test_osci_facet_apply`, `test_index_generate`, `test_corrections_lint`, `test_new_correction`, `test_correction_from_issue`, `test_new_memory`, `test_memory_from_issue`, `test_memory_github_surface`, `test_memory_lint`, `test_memory_conflict_score`, `test_pr_conflict_gate`. (No dedicated `retopic`/`version_apply`/`regime_*` test modules.)

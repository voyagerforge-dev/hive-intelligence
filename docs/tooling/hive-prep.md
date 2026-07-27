# OKF tooling - hive-prep (`hiveprep`)

*Stage 1 of the OKF pipeline: turns raw vendor docs (PDF/DOCX/PPTX/XLSX) into atomic markdown. Conceptual model in [architecture/pipeline.md §3](../architecture/pipeline.md#3-stage-1-document-preparation-hive-prep).*

**Tooling reference:** [Hub](README.md) · **hive-prep** · [hive-gen](hive-gen.md) · [hive-serve](hive-serve.md) · [hive-dbparse](hive-dbparse.md) · [hive-author](hive-author.md) · [hive-zendesk](hive-zendesk.md) · [Architecture & Concepts](../architecture/pipeline.md)

`hiveprep` is a self-contained Python package (CLI entrypoint `hiveprep = hiveprep.cli:cli`) that converts a subtree of messy vendor documents into one clean, single-topic markdown file per source doc, each carrying validated frontmatter. It is a chain of Click subcommands (`scan · dups · validate-plan · dedup-formats · normalize · route · transform · stamp · validate-atomic`), most of them deterministic; the only intelligence is a single LLM curation pass (the `wms-curator` agent) that writes a reviewable `wms-curation.yaml`. Two human review gates bracket the automated steps: **gate 1** approves the curation plan after `validate-plan`, **gate 2** approves the text/vision/passthrough tally after `route` and before any GPU work. The whole chain is orchestrated end-to-end by the [`/wms-prep`](../../.claude/commands/wms-prep.md) command on the dev box via `uv`.

## Module index
| Module | Purpose |
|---|---|
| `cli.py` | Click command group wiring every pipeline stage into a subcommand. |
| `config.py` | Typed `.env`/env-backed `Settings` (paths, model backends, routing thresholds). |
| `scanner.py` | Recursive filesystem walk → streaming inventory CSV with folder-derived hints. |
| `folder_parser.py` | Heuristic classification hints (product/version/category/client) from folder segments. |
| `dups.py` | SHA-256 byte-identical duplicate grouping for the curator. |
| `curation_plan.py` | Load/validate `wms-curation.yaml`; collapse same-family format variants. |
| `slugs.py` | Folder-qualified, collision-safe slug identity for the atomic corpus. |
| `libreoffice.py` | Headless `soffice` DOCX/PPTX/XLSX → PDF conversion with isolated profiles. |
| `striptrim.py` | Deterministic strikethrough/tracked-change removal at the `.docx` XML level. |
| `normalize.py` | Route each source to a PDF intermediate (strike-trim → LibreOffice → copy). |
| `docling_client.py` | HTTP client for Docling on Host-A (text tier: doc bytes → markdown). |
| `vision.py` | Qwen3.6-27B (Host-D) OpenAI-compatible vision client (page image → markdown). |
| `transform.py` | PDF profiling + 3-way tier routing → atomic markdown with frontmatter. |
| `stripper.py` | Product-tunable YAML regex boilerplate scrubbing of converted markdown. |
| `stripper_rules/*.yaml` | Regex rulesets (`default.yaml`, `wmos.yaml`) for the stripper. |
| `stamp.py` | Stamp invariant plan metadata into atomic frontmatter (slug-matched). |
| `validate.py` | Validate the atomic corpus (slugs/enums/links) and derive `relations.yaml`. |

## Modules

### `cli.py`
**Purpose.** The `hiveprep` Click command group; each pipeline stage is one subcommand. Imports are lazy (inside each command body) so a subcommand only pays for the modules it needs.

**Key logic.** Nine subcommands, in pipeline order: `scan` (walks a tree, writes `inventory.csv`, then prints an extension/size stats summary via `_print_stats`), `dups` (byte-identical groups → `dups.yaml`, filtered to the four office extensions), `validate-plan` (loads a plan, prints errors, exits 1 if any), `dedup-formats` (collapses format variants and rewrites the plan YAML with a `generated_by: dedup-formats` manifest), `normalize` (plan includes → PDF intermediates), `route` (GPU-free tier precheck, tallies text/vision/passthrough per doc), `transform` (PDFs + passthrough sources → atomic markdown, constructing the `DoclingClient`/`QwenVisionClient` from settings), `stamp` (writes plan metadata into frontmatter), and `validate-atomic` (validates the corpus, optionally writes `relations.yaml`, exits 1 on errors). `transform` only builds a `DoclingClient` when `prefer_docling and docling_base` are both set, otherwise passes `docling=None` so the text tier degrades to local `pymupdf4llm`.

**Inputs → outputs.** CLI args/options → files on disk (`inventory.csv`, `dups.yaml`, mutated plan YAML, PDFs, atomic `*.md`, `relations.yaml`) plus Rich console output. `validate-plan` and `validate-atomic` set exit code 1 on failure (CI/gate signal).

**Dependencies.** internal: `scanner`, `folder_parser`, `curation_plan`, `dups`, `normalize`, `transform`, `docling_client`, `vision`, `stamp`, `validate`, `config`; external: `click`, `rich`, `PyYAML`.

**Invoked / deployed.** The `hiveprep` console script; driven step-by-step by the `/wms-prep` orchestration command.

### `config.py`
**Purpose.** Single typed settings object for the whole package.

**Key logic.** `Settings(BaseSettings)` with `env_file=".env"` and `extra="ignore"`. Groups: filesystem (`corpus_root`, `work_dir=./wms-work`, `atomic_dir=./wms-work/atomic`), Docling text tier (`docling_base`, `docling_api_key`, `docling_timeout_s=300`, `docling_ca_bundle`, `prefer_docling=True`), Qwen vision tier (`qwen_base`, `qwen_api_key`, `qwen_model=qwen3.6-27b`, `qwen_timeout_s=600`), routing (`vision_min_chars=100`), LibreOffice (`lo_jobs=8`), and boilerplate stripping (`strip_boilerplate=True`, `strip_product=wmos`). `get_settings()` is `@lru_cache`d so one instance is shared. Model backends default to empty strings, so nothing is hardcoded - an empty `docling_base` alone forces the local-only text path.

**Inputs → outputs.** Process env + `.env` → a `Settings` instance.
**Dependencies.** external: `pydantic-settings`.
**Invoked / deployed.** `get_settings()` is called by the `normalize`, `route`, `transform`, and `stamp` CLI commands.

### `scanner.py`
**Purpose.** Build the raw inventory: catalog every file under a subtree with metadata and folder-derived classification hints, streamed so a huge corpus never lands fully in memory.

**Key logic.** `scan_directory` uses `os.walk(followlinks=False)`. When `include_hidden` is false it prunes `dirnames` in place (drops names starting with `.` or `_`) and skips dotfiles. `supported_only` filters to `SUPPORTED_EXTENSIONS` (a broad frozenset covering office, web, text, structured-data, and image formats). Each file is `stat`ed; a `PermissionError`/`OSError` yields an `_error_record` (size `-1`, error text in `category_hint`) instead of crashing; non-regular files are skipped. Folder segments (path parts between root and the file's parent) are passed to the optional `folder_parser` callable, whose exceptions are swallowed as non-fatal. `write_inventory_csv` streams `FileRecord`s to a `csv.DictWriter` (11 columns in `INVENTORY_FIELDS`), optionally showing a Rich progress spinner, and returns the count.

**Inputs → outputs.** A directory `root` → an iterator of `FileRecord` → `inventory.csv` (columns: `relative_path, filename, extension, size_bytes, modified_iso, folder_depth, folder_segments, client_hint, product_hint, version_hint, category_hint`).

**Dependencies.** internal: optional `folder_parser` (injected); external: `rich`.
**Invoked / deployed.** `hiveprep scan`.

### `folder_parser.py`
**Purpose.** Turn SharePoint-style folder hierarchies into a strong classification prior, supplementing (not replacing) the curator's judgment.

**Key logic.** `parse_folder_segments` walks segments left to right, testing each against, in order: `PRODUCT_ALIASES` (normalized folder name → canonical product code, e.g. `warehouse management` → `WMOS`), `VERSION_PATTERN` (a regex matching `v2024`, `9.2.1`, `v2024-SP1`, etc.), and `CATEGORY_KEYWORDS` (folder keyword → `doc_type`, e.g. `config guide` → `config-guide`). A segment that matches none of those and is not in `GENERAL_FOLDERS` (`general`, `shared`, `docs`, …) is collected as a client candidate; the first such candidate becomes `client_hint`. Each hint kind is set only once (first match wins). Returns a dict with only the keys it could fill.

**Inputs → outputs.** `(relative_path, segments)` → `{client_hint?, product_hint?, version_hint?, category_hint?}`.
**Dependencies.** stdlib only (`re`).
**Invoked / deployed.** Imported by `scanner` via the `scan` command (optional import - scanning still works if it is absent).

### `dups.py`
**Purpose.** Give the curator a provable list of byte-identical duplicate sets so exact copies can be deduped with certainty.

**Key logic.** `sha256_file` hashes a file in 1 MiB chunks. `group_duplicates` builds a `{sha256: [paths]}` map and returns only groups with more than one member, each member list sorted. This is content-SHA (exact bytes), distinct from the format-family variant folding in `curation_plan.py`.

**Inputs → outputs.** `list[Path]` → `{sha: [sorted path strings]}` → `dups.yaml` under `duplicate_groups`.
**Dependencies.** stdlib only (`hashlib`).
**Invoked / deployed.** `hiveprep dups` (filtered to `.pdf/.docx/.pptx/.xlsx`).

### `curation_plan.py`
**Purpose.** Load and deterministically validate the curator's `wms-curation.yaml`, and fold same-document format variants down to one representative each. A bad plan refuses to run.

**Key logic.** `Plan` is a dataclass (`scope`, `corpus_root`, `subtree`, `include`, `exclude`, `dedup_groups`, `supersedes`). `load_plan` tolerates missing keys (defaults to empty lists). `validate_plan` returns a list of human-readable errors: paths appearing in both include and exclude; include entries whose `path` is missing on disk (relative to `corpus_root` or an override); and include entries whose `platform`/`product`/`doc_type` fall outside the closed enums `PLATFORMS` (`SCPP`, `SCALE`, `Active`), `PRODUCTS` (`WMS`, `LMS`, `Slotting`, `Omni`, `OMS`, `Billing Management`, `oSCI`), and `DOC_TYPES` (imported from `validate.py` - single source of truth). It also checks `dedup_groups` for keep-in-drop conflicts and missing keep/drop paths. `dedup_format_variants` groups includes by extension-less path, then within each group buckets by format family (`_FMT_FAMILY`: word/ppt/xls), keeping the richest per `_FMT_PRIORITY` (`.docx` > `.doc` > `.rtf`, etc.) and recording the rest as `dedup_groups`. Same-stem files of *different* families (a `.xsd` beside a `.xlsx`) stay distinct, and cross-folder same-name docs are never merged.

**Inputs → outputs.** A YAML plan path → a `Plan`; validation → `list[str]` errors; dedup → a new `Plan` (CLI rewrites it as a `generated_by: dedup-formats` manifest).
**Dependencies.** internal: `validate.DOC_TYPES`; external: `PyYAML`.
**Invoked / deployed.** `hiveprep validate-plan`, `hiveprep dedup-formats`; `Plan`/`load_plan` are also consumed by `normalize`, `transform`, and `stamp`.

### `slugs.py`
**Purpose.** Deterministic, globally-unique slug identity for atomic files, ported from `gwen_prep.manifest` (slug cluster only).

**Key logic.** `doc_slug` kebab-cases `"<product> <folder-qualified-path-without-ext>"` - folder-qualified so same-named docs in different module folders don't collide. `passthrough_slug` appends the extension (`-xsd`, `-xlsx`) so a `.xsd` schema never collides with a same-stem `.xlsx` (both would otherwise drop to the same ext-less slug). `_base_slug` picks `passthrough_slug` for `PASSTHROUGH_EXTS` files, else `doc_slug`. `assign_slugs` walks includes in plan order and disambiguates residual collisions by suffixing `-2`, `-3`, … (first use keeps the clean base). `slugify` (basename-only) remains for direct callers.

**Inputs → outputs.** Plan include entries → one unique slug string per entry (plan order).
**Dependencies.** stdlib only (`re`).
**Invoked / deployed.** Imported by `transform` (slug assignment + `PASSTHROUGH_EXTS`) and `stamp` (slug-matched stamping).

### `libreoffice.py`
**Purpose.** Convert office formats to PDF via headless LibreOffice, safe for parallel batches.

**Key logic.** `to_pdf` checks `soffice` is on PATH (raises `LibreOfficeError` if not), then runs `soffice --headless --convert-to pdf` with a per-call isolated `-env:UserInstallation` profile in a `TemporaryDirectory` so concurrent conversions don't fight over the default profile lock. It enforces a timeout (default 180 s) and verifies a non-empty PDF was actually produced, raising on any failure.

**Inputs → outputs.** A source office file + out dir → the produced `.pdf` path (or `LibreOfficeError`).
**Dependencies.** external: system `soffice` (not a pip dep).
**Invoked / deployed.** Called by `normalize.py`.

### `striptrim.py`
**Purpose.** Remove struck-through / tracked-deletion text from a DOCX before it is rendered, so obsolete content never reaches the converter.

**Key logic.** `strip_struck` walks body paragraphs and (recursively) table-cell paragraphs; `_run_is_struck` inspects each run's `rPr` for `<w:strike/>` or `<w:dstrike/>` (treating a `val` of `false`/`0` as not-struck) and removes matching run elements from the XML tree, counting them in `StripStats`. Deterministic, format-specific to `.docx`.

**Inputs → outputs.** `src` DOCX → cleaned DOCX at `out` + `StripStats(runs_removed)`.
**Dependencies.** external: `python-docx`.
**Invoked / deployed.** Called by `normalize.py` for `.docx` sources only.

### `normalize.py`
**Purpose.** Reduce every supported source to a PDF intermediate the transform step can profile and render.

**Key logic.** `normalize_source` routes by extension: `.pdf` is copied as-is with the suffix lowercased (so transform, which lowercases, finds it); `.docx` is strike-trimmed to `work/clean/` then LibreOffice-converted; all other office formats (`.doc/.docm/.ppt/.pptx/.xls/.xlsx`) go straight through LibreOffice (treated as clean - strike-trim only edits `.docx` XML). Every failure is captured in a flagged `NormalizeResult(ok=False, error=...)` rather than raised, so one bad file never aborts the batch. `normalize_plan` runs includes concurrently via a `ThreadPoolExecutor` (each `soffice` call already isolated), and is resumable: `skip_existing` short-circuits includes whose output PDF already exists. `normalize_dir` is a directory-mode variant that skips anything already under the work dir.

**Inputs → outputs.** Plan includes (or a dir) → PDFs under `work/pdf/` + `NormalizeResult`s.
**Dependencies.** internal: `striptrim`, `libreoffice`; stdlib `concurrent.futures`.
**Invoked / deployed.** `hiveprep normalize`.

### `docling_client.py`
**Purpose.** HTTP client for the Docling gateway on Host-A (the preferred text-tier converter).

**Key logic.** `DoclingClient.to_markdown` POSTs the file bytes to `<base>/v1/convert/file` with `to_formats=md, do_ocr=false` (born-digital corpus, OCR off, tables preserved as markdown). It sends an `Authorization: Bearer` header only when an API key is set (Docling on the LAN is keyless; an empty key would emit a malformed `Bearer ` header httpx rejects). Non-200 raises `DoclingError`; a 200 with empty `md_content` raises `EmptyConversion` (a `DoclingError` subclass) so the transform layer can fall back. Verifies TLS against `ca_bundle` when provided.

**Inputs → outputs.** `(filename, content bytes)` → markdown string (or `DoclingError`/`EmptyConversion`).
**Dependencies.** external: `httpx`.
**Invoked / deployed.** Constructed in the `transform` CLI command; used by `transform.extract_text_markdown`.

### `vision.py`
**Purpose.** Vision-tier converter: render a page image to clean markdown and describe figures/diagrams that text extraction drops. Replaces the retired GLM-4.1V tier (same OpenAI shape).

**Key logic.** `QwenVisionClient.describe_image` base64-encodes the PNG into a `data:image/png;base64` `image_url` and POSTs an OpenAI-compatible `/v1/chat/completions` body (`temperature=0.0`, `max_tokens=16000`) with `PAGE_PROMPT` instructing GitHub-flavored markdown, tables preserved, and italic factual figure descriptions. The response `content` is passed through `strip_think`, which removes `<think>…</think>` spans (and un-closed `<think>` tails) and unwraps `<answer>…</answer>` if present - belt-and-suspenders for reasoning models whose thoughts may leak into `content` rather than `reasoning_content`. Non-200 raises `VisionError`.

**Inputs → outputs.** PNG bytes (+ optional prompt) → markdown string (or `VisionError`).
**Dependencies.** external: `httpx`.
**Invoked / deployed.** Constructed in the `transform` CLI command; used per rendered page by `transform.transform_pdf`.

### `transform.py`
**Purpose.** The converter core: profile each normalized PDF, route it to one of three tiers, strip boilerplate, and write the atomic markdown file with frontmatter.

**Key logic.** `pdf_text_profile` (PyMuPDF/`fitz`) computes pages, average extractable chars/page, and `img_page_frac` - the fraction of pages dominated by a single large image (per-page *largest* image area as a fraction of page area, not summed, so recursive small logos don't inflate it). `route_tier` decides: `avg_chars >= vision_min_chars` (default 100) → `text`; otherwise `text` unless `img_page_frac >= 0.5` (`VISION_MIN_IMG_PAGES`), in which case `vision`. `transform_pdf` applies the route (an explicit `force_tier` from a routing override wins). Text tier calls `extract_text_markdown`, which prefers Docling and falls back to local `pymupdf4llm` on any `DoclingError`/empty conversion (so it runs GPU-free); `_clean_text_md` strips data-URI images, collapses 4+-dot leaders, and squeezes blank-line runs. Vision tier renders pages with `pdftoppm -png -r 100` and concatenates per-page `vision.describe_image` output. `passthrough_markdown` fences already-text sources (`.vm/.xsd/.xml/.json/.csv/.properties/.sql/.txt`) with a language hint. `_write_atomic` emits frontmatter (`title/slug/source_doc/extracted_via/status: active`) plus an H1 and body. Both text and vision bodies pass through `_strip` (the boilerplate stripper) unless disabled; passthrough never does. `transform_plan` assigns slugs across valid includes, skips already-written slugs (resumable), dispatches passthrough vs PDF paths, and - like normalize - captures every per-doc failure as a flagged `TransformResult(ok=False)` rather than crashing. `route_plan` is the GPU-free precheck powering gate 2: it profiles each PDF and reports the tier/pages/avg_chars/img_page_frac without converting anything.

**Inputs → outputs.** A `Plan` + `work_dir` → atomic `*.md` under `work/atomic/` + `TransformResult`s (or `RouteResult`s for the precheck).
**Dependencies.** internal: `curation_plan`, `docling_client`, `slugs`, `stripper`; external: `pymupdf`/`fitz`, `pymupdf4llm`, system `pdftoppm` (poppler); injected `docling`/`vision` clients.
**Invoked / deployed.** `hiveprep route` (precheck) and `hiveprep transform` (conversion).

### `stripper.py`
**Purpose.** Scrub copyright/trademark/confidentiality/page-number boilerplate from converted markdown via product-tunable YAML regex rules.

**Key logic.** `load_stripping_rules` reads `stripper_rules/<product>.yaml`, falling back to `default.yaml` when the product ruleset is absent, and compiles each `pattern` with any of the `MULTILINE`/`IGNORECASE`/`DOTALL` flags named in its `flags` string. `_apply` runs every compiled pattern's `subn("")` in sequence, tallies match counts, then collapses `\n{3,}` runs the deletions leave behind and strips. `strip_boilerplate` returns a `StrippingResult` with cleaned text plus diagnostics (`original_length`, `stripped_length`, `regex_matches`, `product`). This is the Layer-2 regex layer ported from the retired gwen-platform stripper; the original Layer-1 *structural* header/footer removal (which needed the DoclingDocument model) is a documented follow-up since hive-prep's converter returns markdown text, not the doc model.

**stripper_rules.** `default.yaml` - generic line-oriented rules: `Page N of M` footers, copyright lines with a year, `All Rights Reserved`, and TOC dot-leaders resolving to a page number. `wmos.yaml` - Manhattan-specific and deliberately *footer/header-form-scoped* so rules can't eat real prose (the corpus is Manhattan docs, so a bare "starts with Manhattan/Confidential" would be far too broad): bare `Manhattan Associates` footer lines, vendor name co-occurring with a legal marker on one line, footer-shaped confidentiality lines, page footers, year-bearing copyright, `All Rights Reserved`, and standalone trademark-notice lines - plus the same dot-leader rule.

**Inputs → outputs.** `(markdown_text, product)` → `StrippingResult`.
**Dependencies.** external: `PyYAML`.
**Invoked / deployed.** Called by `transform._strip` for text and vision tiers (never passthrough), gated by `strip_boilerplate`/`strip_product` settings.

### `stamp.py`
**Purpose.** Fill invariant metadata (`platform/product/version/doc_type/topic/source_doc`) into atomic frontmatter deterministically, since the LLM is unreliable at echoing batch-constant fields.

**Key logic.** `stamp_from_plan` matches each `*.md` to its plan include entry by the folder-qualified `slug` (via `assign_slugs`), *not* the basename - many WMS docs share a basename across module folders, so basename matching would misstamp all but one. Values are coerced through `_yaml_scalar` (quotes numeric-looking or YAML-reserved scalars like `true`/`no`). `stamp_file` parses the `---` fence, and by default only adds *missing* fields (`only_missing`, i.e. content-trust: preserves values the subagent already wrote); with `--overwrite` it replaces them. New lines are inserted right after the `slug:` line when present, else at the top. Files without a valid frontmatter fence are skipped.

**Inputs → outputs.** `atomic_dir` + `Plan` → mutated `*.md` frontmatter + `{filename: [changed fields]}`.
**Dependencies.** internal: `slugs.assign_slugs`; external: `PyYAML`.
**Invoked / deployed.** `hiveprep stamp`.

### `validate.py`
**Purpose.** Final acceptance check on the atomic corpus and derivation of `relations.yaml`. Also the canonical home of the `DOC_TYPES` enum.

**Key logic.** `validate_atomic_dir` parses each file's frontmatter and accumulates errors (never raises past the first): duplicate `slug`; missing `slug`; `doc_type` outside `DOC_TYPES`; `status` outside `{active, superseded}`; and missing required `platform`/`product`/`version`. It then derives edges from `related` (each target must resolve to a known slug via `_strip_version`, which trims a `@version` suffix - dangling targets are errors) and `supersedes` (recorded as edges; targets may be intentionally absent so they warn-as-edge only). `_has_cycle` runs a white/gray/black DFS over the resolvable `supersedes` edges and flags any cycle. Relations are *derived* from frontmatter so nothing races to write a shared file. `write_relations` dumps the edge graph to YAML.

**Inputs → outputs.** `atomic_dir` → `ValidationReport(errors, relations, slugs)`; optional `relations.yaml`. CLI exits 1 on any error.
**Dependencies.** external: `PyYAML`.
**Invoked / deployed.** `hiveprep validate-atomic`; `DOC_TYPES` is imported by `curation_plan.py`.

## Deployment & runtime
hive-prep has **no deploy directory** - it is a dev-box tool, not a hosted service. It runs from the package root under `uv` and is orchestrated by the [`/wms-prep`](../../.claude/commands/wms-prep.md) command, which walks the subcommands in order through the two human gates (gate 1 after `validate-plan`, gate 2 after `route`). The intelligence lives in a single up-front LLM curation pass (the `wms-curator` agent producing `wms-curation.yaml`); everything downstream is deterministic code.

It calls two model backends, both configured via `.env`/env through `config.Settings` and **never hardcoded**:

- **Text tier - Docling on Host-A** (`docling_base`, `docling_api_key`, `docling_ca_bundle`, `prefer_docling`). LAN-keyless in practice; an empty `docling_base` (or any Docling failure) transparently falls back to local `pymupdf4llm`, so the pipeline runs with no GPU.
- **Vision tier - Qwen3.6-27B on Host-D** (`qwen_base`, `qwen_api_key`, `qwen_model`, `qwen_timeout_s`), an OpenAI-compatible VLM used for scanned/image-dominant docs.

Other env/config it reads: `corpus_root`, `work_dir` (default `./wms-work`, holding `pdf/`, `clean/`, `atomic/`, `_pages/`), `atomic_dir`, `vision_min_chars` (routing threshold), `lo_jobs` (LibreOffice parallelism), and `strip_boilerplate`/`strip_product`. System dependencies outside pip: `soffice` (LibreOffice, for `normalize`) and `pdftoppm` (poppler, for vision-tier page rendering).

## Tests
The suite is **fakes-only** - no live model or network access. Docling/Qwen HTTP is exercised through `respx`/`httpx` mocking (a dev-only optional dependency), LibreOffice and `pdftoppm` are stubbed, and validation/routing/slug/stripper logic is pure-function tested. There is one test module per source module under `tests/` (`test_cli.py`, `test_transform.py`, `test_stripper.py`, `test_validate.py`, …), roughly **117 test functions** total.

Run them from the package root:

```
cd tooling/hive-prep && uv run pytest -q
```

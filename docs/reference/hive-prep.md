# hive-prep

Raw documents to atomic markdown. Package `hiveprep`, CLI `hiveprep`.

Narrative version: [building a corpus](../guides/building-a-corpus.md).

## Commands

A chain of Click subcommands, run in order. Each writes files the next reads, so the pipeline is
resumable and every intermediate state is inspectable on disk.

| Command | Does |
|---|---|
| `scan` | walk a tree, produce a file inventory CSV with folder-derived hints |
| `dups` | report byte-identical duplicate sets |
| `dedup-formats` | collapse same-document format variants, such as `X.doc` alongside `X.docx` |
| `validate-plan` | validate the curation plan before execution **(gate 1)** |
| `normalize` | normalise the plan's includes to PDF intermediates |
| `route` | report the text, vision and passthrough tier split, without using a GPU **(gate 2)** |
| `transform` | convert to atomic markdown |
| `stamp` | stamp plan metadata into atomic frontmatter |
| `validate-atomic` | validate the corpus: unique slugs, enums, links |

`hiveprep <command> --help` for arguments.

Only one step involves a model: the curation pass that produces the plan. Everything else is
deterministic.

## Two gates

**Gate 1, after `validate-plan`.** The curation plan lists every source document with a proposed
decision: include, exclude, duplicate-of, supersedes, plus derived metadata. Validation checks the
plan is well formed. It cannot check that it is *right*, and nothing downstream will notice that
you meant to exclude a directory.

**Gate 2, after `route`.** `route` is a GPU-free precheck reporting how many files will go through
each conversion tier. Approving it before `transform` is what stops a surprise vision-model bill.

## Modules

| Module | Purpose |
|---|---|
| `cli.py` | Click command group wiring each stage to a subcommand |
| `config.py` | typed environment-backed settings |
| `profile.py` | the corpus profile, as far as this package needs it: the folder-name aliases mapping a directory segment to a product |
| `scanner.py` | recursive walk to a streaming inventory CSV |
| `folder_parser.py` | classification hints from folder segments |
| `dups.py` | SHA-256 duplicate grouping |
| `curation_plan.py` | load and validate the plan; collapse format variants |
| `slugs.py` | folder-qualified, collision-safe slug identity |
| `libreoffice.py` | headless conversion to PDF with isolated profiles |
| `striptrim.py` | strikethrough and tracked-change removal at the document XML level |
| `normalize.py` | route each source to a PDF intermediate |
| `docling_client.py` | HTTP client for the document converter |
| `vision.py` | OpenAI-compatible vision client, page image to markdown |
| `transform.py` | PDF profiling, tier routing, atomic markdown with frontmatter |
| `stripper.py` | YAML regex boilerplate scrubbing |
| `stripper_rules/*.yaml` | the rule sets |
| `stamp.py` | stamp plan metadata into frontmatter, matched by slug |
| `validate.py` | validate the atomic corpus and derive relations |

## Conversion tiers

Three, chosen per file.

**Text.** A document converter service, when `DOCLING_BASE` is set and `PREFER_DOCLING` is true.
Handles PDF, DOCX, PPTX and XLSX including layout and tables.

**Vision.** A vision model, for pages that yield almost no extractable text: scans and image-only
slides. A page producing fewer than `VISION_MIN_CHARS` characters routes here.

**Passthrough.** Already-text sources, copied with frontmatter added.

LibreOffice runs locally as the conversion fallback; `LO_JOBS` sets concurrency.

If the vision model is unavailable the pipeline continues without it and those pages come through
thin. That degradation is deliberate: a stalled pipeline is worse than a corpus with a few known
gaps, and `validate-atomic` shows you which files are suspiciously short.

## Boilerplate stripping

Regex rules in `hiveprep/stripper_rules/<product>.yaml`, selected by `STRIP_PRODUCT`, disabled with
`STRIP_BOILERPLATE=false`. Each rule is line-oriented: matching lines are deleted, then blank-line
runs collapse. Never applied to fenced code blocks.

```yaml
product: default
patterns:
  - type: regex
    pattern: "^\\s*Page \\d+ of \\d+\\s*$"
    flags: MULTILINE
```

Note the doubled backslashes. These are YAML double-quoted scalars, where a lone `\s` is an invalid
escape and fails to parse.

The product ships **only `default.yaml`**: page footers, copyright lines, rights notices. Vendor
rule sets are corpus-side and belong with your corpus.

**Anchor rules to footer and header form, never to a vendor name alone.** In a corpus of one
vendor's manuals, that name appears in thousands of legitimate sentences, and a rule matching the
bare name deletes content while looking like it is working. The test suite covers this case
specifically.

## Internals

Module-level detail: the algorithms, thresholds and failure behaviour. Verified against the code
on 2026-07-30.

### `scanner.py`, `folder_parser.py`, `dups.py`

`scanner` walks a tree and *streams* an inventory CSV rather than building a list, so a corpus
larger than memory still scans. `folder_parser` derives classification priors from folder segments,
which the curation agent treats as hints rather than facts. `dups` groups by SHA-256, so it finds
byte-identical files under different names and misses near-duplicates by design; near-duplicate
judgment is the curation agent's job.

### `curation_plan.py`

Loads the plan and validates it deterministically: enum membership, path existence, no duplicate
slugs. Also collapses same-stem format variants **family-aware**: `.doc`/`.docx`/`.docm` are one
family, `.ppt`/`.pptx` another, `.xls`/`.xlsx` another. Same stem *across* families stays distinct,
because `Spec.docx` and `Spec.xlsx` are usually two documents, not two renderings of one.

### `slugs.py`

Slugs are folder-qualified and collision-safe. Identity is the slug, so a collision silently merges
two documents into one atomic file; the qualification is what prevents it.

### `libreoffice.py`, `striptrim.py`, `normalize.py`

`libreoffice` converts office formats to PDF headlessly, each job with an **isolated user profile**
directory, because concurrent headless LibreOffice instances sharing a profile corrupt each other.
`LO_JOBS` sets concurrency.

`striptrim` removes strikethrough and tracked-change text at the **document XML level**, before
conversion. Doing it afterwards is not equivalent: once a `.docx` is a PDF, deleted text that was
still visible is indistinguishable from live text.

`normalize` routes each source to a PDF intermediate: strike-trim then convert for `.docx`,
LibreOffice for other office formats, straight copy for PDFs.

### `transform.py`, the converter core

The most consequential module. Three parts.

**Profiling.** `pdf_text_profile` reports pages, average extractable characters per page, and
`img_page_frac`, the fraction of pages dominated by one large image.

> The dominant-image test uses each page's **largest single image**, not the sum of its images.
> Summing inflates the fraction on any page carrying several small recurring logos, which would
> route text-rich pages to the vision tier and quietly multiply the GPU bill.

**Routing.** `route_tier` is deliberately simple:

```
avg_chars >= VISION_MIN_CHARS (100)              -> text
otherwise, img_page_frac >= VISION_MIN_IMG_PAGES (0.5) -> vision
otherwise                                        -> text
```

A page counts as image-dominated when its largest image covers `IMG_DOMINANT_FRAC` (0.5) of the
page. **Text is the default in both undecided branches**: a thin text extraction is a cheap, visibly
short file, whereas a wrong vision route is expensive and looks fine.

An explicit per-slug `force_tier` from a routing override beats the automatic decision.

**Conversion.** The text tier calls `extract_text_markdown`, which prefers the document converter
and **falls back to local `pymupdf4llm` on any converter error or empty result**, so the pipeline
runs with no GPU and no converter service. `_clean_text_md` strips data-URI images, collapses
four-or-more dot leaders, and squeezes blank-line runs.

The vision tier renders pages with `pdftoppm -png` at a configured DPI and concatenates per-page
descriptions. `passthrough_markdown` fences already-text sources with a language hint.

Text and vision output both pass through the boilerplate stripper. **Passthrough never does**: you
do not regex-scrub fenced code.

**Two behaviours that matter when a run goes wrong:**

- **Resumable.** `transform_plan` skips any slug whose atomic file already exists (`skip_existing`),
  reporting it with `tier="skip"`. Re-running after a partial failure converts only what is missing.
- **Failures are captured, not raised.** A per-document error becomes a flagged
  `TransformResult(ok=False, error=…)` and the run continues. One unreadable file in three thousand
  does not abort the batch, and the failures are listed at the end.

`route_plan` is the same profiling without any conversion. That is gate 2: it tells you the tier
split before you pay for it.

### `stamp.py`, `validate.py`

`stamp` writes plan metadata into atomic frontmatter, **matched by slug**, filling only missing
fields unless overwrite is set, so a hand-corrected value survives a re-stamp. It refuses when
neither `ATOMIC_DIR` nor `--atomic` is set, and when the directory they name is not there, naming
whichever of the two the value came from: stamping nothing prints "0 files stamped" and exits 0,
which is also what a correct re-run over an already-stamped corpus prints.

`validate` checks unique slugs, `doc_type` enum membership and resolvable links, and derives
`relations.yaml`. It exits non-zero on any error, which is what makes it usable as a gate in CI.

## Tests

Fakes only. The Docling and vision clients are injected, so the suite runs with no network, no GPU
and no converter service. Tests that need LibreOffice skip with a stated reason when it is absent.
Use `uv run pytest --collect-only -q` in `tooling/hive-prep/` for the current inventory rather than
a count written down here.

## Configuration

See [configuration](configuration.md#hive-prep).

## Gotchas

**`WORK_DIR` gets large.** It holds intermediate conversions for the whole corpus. It is scratch and
safe to delete between runs.

**Scanning is content-hashed, not path-based.** The same document under two names is one entry with
two paths. Usually what you want, occasionally surprising.

**A bad plan refuses to run.** Deliberate: a plan that half-applies is harder to reason about than
one that does not start.

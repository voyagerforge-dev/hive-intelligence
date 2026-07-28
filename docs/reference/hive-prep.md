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

## Configuration

See [configuration](configuration.md#hive-prep).

## Gotchas

**`WORK_DIR` gets large.** It holds intermediate conversions for the whole corpus. It is scratch and
safe to delete between runs.

**Scanning is content-hashed, not path-based.** The same document under two names is one entry with
two paths. Usually what you want, occasionally surprising.

**A bad plan refuses to run.** Deliberate: a plan that half-applies is harder to reason about than
one that does not start.

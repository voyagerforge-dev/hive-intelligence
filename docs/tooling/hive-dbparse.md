# OKF tooling - hive-dbparse (`hivedbparse`)

*The deterministic, LLM-free parser (dep: `sqlglot`) that builds the WMOS database-object card tier from the Manhattan deploy DDL. Conceptual model in [architecture/pipeline.md](../architecture/pipeline.md#the-database-object-tier-hive-dbparse).*

**Tooling reference:** [Hub](README.md) · [hive-prep](hive-prep.md) · [hive-gen](hive-gen.md) · [hive-serve](hive-serve.md) · **hive-dbparse** · [hive-author](hive-author.md) · [hive-zendesk](hive-zendesk.md) · [Architecture & Concepts](../architecture/pipeline.md)

`hive-dbparse` turns the Manhattan WMOS deploy DDL (Oracle + DB2 `CREATE TABLE`/`COMMENT`/`ALTER`/`CREATE INDEX`/`CREATE SEQUENCE` and `CREATE [OR REPLACE]` PL/SQL units under `ManhDBDeploy/{Oracle,DB2}/DBScripts/Product/*.sql` and the base-schema catalogs under `.../DBScripts/Seed/Product/<module>/`) into OKF `dbobject` cards under `concepts/wms/db/`. The flow is **parse (per dialect) -> reconcile (union Oracle+DB2) -> gate -> emit**: `parse_tables`/`parse_aux`/`parse_plsql` read each dialect independently, `reconcile` unions the two into one dialect-tagged model per object, `run` enforces a hard verification gate (no unparsed construct may be silently dropped), and `emit` renders one markdown card per surviving object plus a manifest. It is deterministic and LLM-free because every step is driven by `sqlglot`'s tokenizer/AST and exact character-slice arithmetic - the same input always yields byte-identical cards, and PL/SQL bodies are copied verbatim rather than summarized. It runs once on the dev box; there is no `deploy/` directory.

## Module index
| Module | Purpose |
|---|---|
| `model.py` | The three dataclasses (`Column`, `Table`, `PlsqlObject`) that carry parsed schema state. |
| `parse_tables.py` | Parse `CREATE TABLE` into `Table`s via sqlglot AST, with token-level fallbacks for storage/constraint-state noise. |
| `parse_aux.py` | Attach comments, FKs, indexes and sequences from `COMMENT ON`/`ALTER`/`CREATE INDEX`/`CREATE SEQUENCE` onto existing `Table`s. |
| `parse_plsql.py` | Slice `CREATE [OR REPLACE]` PL/SQL units into `PlsqlObject`s by tokenizer boundary detection; bodies captured verbatim. |
| `reconcile.py` | Union the independent Oracle and DB2 parse runs into one dialect-tagged model per object. |
| `emit.py` | Render `Table`/`PlsqlObject` into `dbobject` markdown cards + manifest lines. |
| `run.py` | End-to-end runner: walk the tree, parse both dialects, reconcile, run the verification gate, write cards + `manifest.jsonl` (+ `conflicts.log`). |

## Modules

### `model.py`
**Purpose.** Defines the three plain dataclasses that every stage reads and mutates. No logic beyond field defaults.

**Key logic.** `Column` holds `name`, per-dialect `type_oracle`/`type_db2` (either may stay `None` when the column is absent from that dialect), `not_null`, and a verbatim `comment` from `COMMENT ON COLUMN`. `Table` holds `name`, `module`, verbatim `comment`, `columns`, `pk` (list of names), `fks` (list of `(col, ref_table, ref_col)` tuples), `indexes` (`(name, cols, unique)`), `sequences`, `triggers`, a `dialects` set (`{"oracle","db2"}`), and `source_files` (repo-relative paths, filled by the runner; empty lets `emit` fall back to a synthesized path). `PlsqlObject` holds `name`, `module`, `kind` (`package|procedure|function|view|trigger`), `signature`, per-dialect verbatim `body_oracle`/`body_db2`, `comment`, `dialects`, and `source_files`.

**Inputs -> outputs.** None (data carrier). Instances are constructed by the parsers and mutated by `parse_aux`/`reconcile`/`run`.

**Dependencies.** internal: none; external: `dataclasses` only.

**Invoked / deployed.** Imported everywhere.

### `parse_tables.py`
**Purpose.** Parse every `CREATE TABLE` in a dialect's SQL text into `{table_name: Table}`. AST-driven exclusively - never regex - so nested type parens (`NUMBER(20,0)`), quoted identifiers, inline `--` comments and multi-line statements are handled exactly.

**Key logic.**
- **Dialect resolution.** `_SQLGLOT_DIALECT` maps the *logical* label `"oracle"` -> `"oracle"` and `"db2"` -> `None`. sqlglot 30.x has **no native db2 dialect**, so DB2 DDL is parsed with the generic/ANSI dialect (`None`); the logical label is still kept for tagging (`type_db2`, `Table.dialects`). An unknown label raises `ValueError`.
- **Statement splitting.** `_split_statements` tokenizes with the dialect's own tokenizer and cuts on top-level `SEMICOLON` tokens, then returns exact source substrings via `sql[chunk[0].start : chunk[-1].end + 1]` - a `;` inside a string or comment is never a separator, and text is never regenerated.
- **Pre-parse cleanup** (applied to each statement before any parse attempt, so both the direct attempt and the fragment fallback benefit):
  - `_strip_constraint_state` removes trailing Oracle constraint-state keywords (`ENABLE`/`DISABLE`/`VALIDATE`/`NOVALIDATE`), which sqlglot's grammars don't model. A match is a bare `VAR` token whose text is one of those keywords and whose next token is a comma, the table's closing paren, or another such keyword (so `ENABLE VALIDATE` chains strip whole). Dropped by char-slice, not regex.
  - `_strip_using_index_clause` removes Oracle's `USING INDEX [TABLESPACE ...]` clause that trails a table-level constraint *inside* the column-list parens (the paren-matching fallback can't trim it because it sits inside the parens). For each `USING` followed by `INDEX`, it drops from `USING` up to the next `,` or `)` at the same-or-shallower paren depth.
  - `_normalize_current_registers` rewrites DB2's bare `CURRENT TIMESTAMP`/`CURRENT DATE`/`CURRENT TIME` special registers into underscored form the generic grammar accepts, by splicing the whitespace gap between a bare `VAR` `CURRENT` and a following `TIMESTAMP`/`DATE`/`TIME` token into a single `_`. A quoted `"CURRENT"` tokenizes as `IDENTIFIER`, not `VAR`, so a real column named `CURRENT` is untouched.
- **Parse + fragment fallback.** It first tries `sqlglot.parse_one` on the cleaned text. If that yields no `CREATE TABLE`, `_extract_create_table_fragment` isolates a bare `CREATE TABLE name (...)` by token-level paren-depth counting: find the first `L_PAREN`, walk to its matching `R_PAREN` at depth 0, and slice `text[tokens[0].start : tokens[close_idx].end + 1]`. This trims dialect-specific physical-storage tails (`TABLESPACE`, `STORAGE (...)`, `PCTFREE`) that sqlglot rejects - Oracle storage clauses degrade to this token fallback. The fragment is re-parsed.
- **CTAS skip.** `_is_ctas` detects `CREATE TABLE ... AS SELECT` (kind `TABLE`, `this` is a bare `exp.Table` with a query `expression`, no column list). CTAS has no columns to card, so it is logged at INFO and skipped - not a gate failure.
- **Build.** `_build_table` walks `exp.ColumnDef` nodes: `not_null` from any `NotNullColumnConstraint`; column type via `col_type.sql(dialect=sqlglot_dialect)` assigned to `type_db2` or `type_oracle` per logical dialect; PK from inline `PrimaryKeyColumnConstraint`s plus table-level `exp.PrimaryKey` expressions.
- **Gate signal.** When no `CREATE TABLE` is found and it is not CTAS, `_looks_like_create_table` decides WARNING vs. silence: token-driven, the first token must be `CREATE` and the first non-modifier token after it (skipping `TEMPORARY`/`GLOBAL`/`PRIVATE`/`SHARED`) must be the `TABLE` keyword. A real `CREATE TABLE` that failed to parse logs a WARNING (which the runner turns into a gate failure); a `CREATE SEQUENCE`/`TYPE`/`MATERIALIZED VIEW` stays silent even if the substring `TABLE` appears later.

**Inputs -> outputs.** `parse_tables(sql, dialect) -> dict[str, Table]`. `Table.module` is left `""` (the runner sets it from the filename).

**Dependencies.** internal: `model`; external: `sqlglot` (`exp`, `Dialect`, `TokenType`), `logging`.

**Invoked / deployed.** Called per module file by `run._parse_dialect_tables`.

### `parse_aux.py`
**Purpose.** Mutate the already-built `Table`s in place with comments, FKs, indexes and sequences parsed from the remaining statement types. Statements referencing an unknown table (or unparseable at all) are logged and skipped - never allowed to crash the run.

**Key logic.**
- Reuses `_sqlglot_dialect` and `_split_statements` from `parse_tables`, then parses each statement individually with `sqlglot.parse_one`; a parse exception logs a WARNING and continues (aux failures do **not** feed the gate - see note below).
- `_apply_node` dispatches by AST node type: `exp.Comment` -> `_apply_comment`; `exp.Alter` -> `_apply_alter_table`; `exp.Create` with kind `INDEX`/`SEQUENCE` -> the matching applier; `exp.Command` (a statement sqlglot degraded to an opaque command) is logged and skipped; anything else (GRANT, `CREATE TABLE`, ...) is ignored.
- `_apply_comment` handles `COMMENT ON TABLE` (sets `Table.comment`) and `COMMENT ON COLUMN` (sets `Column.comment`); comment text is taken verbatim from the `exp.Literal`. An unknown table/column logs a WARNING and returns.
- `_apply_alter_table` walks `exp.ForeignKey` nodes under an `ALTER TABLE`, reads the `reference` target table and columns, and `zip`s the FK's local columns with the referenced columns into `Table.fks`.
- `_apply_create_index` reads the index name and `params.columns` (unwrapping `exp.Ordered` to the underlying column), plus the `unique` flag, and appends `(name, cols, unique)` to `Table.indexes`.
- `_apply_create_sequence` attaches a sequence to its owning table via a **name-prefix heuristic**: `_strip_sequence_affixes` removes `_SEQUENCE`/`_SEQ`/`SEQUENCE_`/`SEQ_`, then `_sequence_owner` picks the table whose upper-cased name is the longest exact/prefix match against the remaining stem (`stem == upper`, `stem.startswith(upper + "_")`, or `upper.startswith(stem)`). No match logs a WARNING and drops the sequence (an orphan).

**Inputs -> outputs.** `apply_aux(tables, sql, dialect) -> None` (mutates `tables`).

**Dependencies.** internal: `model`, `parse_tables` (`_sqlglot_dialect`, `_split_statements`); external: `sqlglot`, `logging`.

**Invoked / deployed.** Called once per dialect by `run._parse_dialect_tables` on the concatenation of all that dialect's module texts (so an `ALTER`/`COMMENT` in one file can attach to a table defined in another).

### `parse_plsql.py`
**Purpose.** Split top-level `CREATE [OR REPLACE]` PL/SQL units (`PACKAGE[ BODY]`, `PROCEDURE`, `FUNCTION`, `TRIGGER`, `VIEW`) into `PlsqlObject`s. PL/SQL bodies are **never** handed to `sqlglot.parse_one` - only the dialect *tokenizer* is used to find unit boundaries, then the original text is sliced.

**Key logic.**
- **Verbatim capture.** The entire module is tokenized once. Unit boundaries are character offsets from tokens, and each body is `sql[start_char:end_char]` - a byte-for-byte slice of the original source, so author formatting is preserved. Bodies are never reconstructed from tokens.
- **Kind detection.** `_find_unit_starts` scans for `CREATE`, optionally consumes `OR REPLACE` (both `CREATE OR REPLACE ...` and bare `CREATE TRIGGER`/`CREATE VIEW` are matched - inline module-file triggers/views are often bare), then calls `_match_kind`. `_match_kind` first skips optional Oracle view modifiers (`FORCE`/`NO`/`EDITIONABLE`/`NONEDITIONABLE`, all plain `VAR` tokens) via `_skip_optional_view_modifiers`, then maps `PROCEDURE`/`FUNCTION`/`TRIGGER`/`VIEW` token types to their kind. `PACKAGE`, `BODY`, `SYNONYM`, `VARIABLE`, `TYPE` are not sqlglot keywords (they tokenize as `VAR`) and are matched by text; `PACKAGE BODY` and `TYPE BODY` are recognized as two-token forms. `SEQUENCE` has its own token type.
- **Skip kinds.** `SKIP_KINDS = {variable, type, type body, sequence, synonym}` are *recognized* (so they are never misreported as unrecognized units) but deliberately not carded: DB2 global variables, user-defined collection/object TYPEs, DB2 `CREATE OR REPLACE SEQUENCE` (handled table-side by `parse_aux`), and synonyms. They are logged at INFO and skipped.
- **Unrecognized-unit gate signal.** `_find_unrecognized_units` finds every `CREATE OR REPLACE` whose following object-kind keyword `_match_kind` can't classify (a typo'd `PROCEEDURE`, an unsupported kind). Since `CREATE OR REPLACE` unambiguously introduces a replaceable object, these are intended units that parsed to nothing - each logs a WARNING that the runner routes into `unparsed`, failing the gate. (This check is applied only to `CREATE OR REPLACE`, not bare `CREATE`.)
- **Boundary detection (`/` rule).** `_unit_end_char` ends a unit at the next **standalone** `/` (the SQL*Plus terminator) strictly before the next unit's start, else at that next start / end of source. `_is_standalone_slash` confirms a `/` is standalone by pure char inspection: only whitespace from the line start up to the `/`, and only whitespace after it to the newline/EOF. A `/` used as arithmetic division always has a non-whitespace operand on its line, so the two are distinguished without regex.
- **Signature.** `_signature_end_char` ends the header at the first `AS`/`IS`/`BEGIN` (`_SIGNATURE_TERMINATORS`) after the name; `signature = sql[start_char:sig_end_char].strip()`.
- **Name.** `_dotted_name_end` consumes `ident (DOT ident)*` so `SCHEMA."FOO"` is kept whole; the name is built from token *text* (quotes already stripped by the tokenizer) so it comes out clean and unquoted, mirroring `parse_tables`.

**Inputs -> outputs.** `parse_plsql(sql, dialect) -> list[PlsqlObject]` with body in `body_oracle` or `body_db2` per dialect. A package emits two same-name objects here (spec and body) - `reconcile` merges them later.

**Dependencies.** internal: `model`, `parse_tables` (`_sqlglot_dialect`); external: `sqlglot` (`Dialect`, `Token`, `TokenType`), `logging`.

**Invoked / deployed.** Called by `run` on BOTH the dedicated `PLSQL_Objects/*.sql` files (`_parse_dialect_plsql`) AND inline on each `Product/*.sql` module text (`_parse_dialect_tables`), so a trigger/view declared inline in a table module is captured too.

### `reconcile.py`
**Purpose.** The only place the independent Oracle and DB2 runs are compared. Unions them into one dialect-tagged model per object without mutating either input.

**Key logic.**
- `reconcile_tables` unions by name in Oracle-first order. For a name in both dialects, the **Oracle `Table` is authoritative for structure** (comment/pk/fks/indexes/sequences/triggers); DB2 only contributes `type_db2` onto columns matched by name, and a DB2-only column is appended (with Oracle type left `None`). `dialects` is the union. Inputs are deep-copied via `dataclasses.replace` so neither source is mutated.
- **Package collapse.** `_merge_package_units` runs per dialect first: `parse_plsql` emits a package's spec and body as two same-name `kind="package"` objects, so this collapses the pair into one - the spec's text becomes `signature`, the body's text becomes `body_<dialect>`. Spec-vs-body is discriminated by `_looks_like_package_body`, a `CREATE OR REPLACE PACKAGE BODY` prefix check (this is the one regex in the module, used only as an anchored keyword match). Non-package units pass through unchanged.
- `reconcile_plsql` then unions the collapsed lists by name (Oracle-first). For a name in both, `dialects` is unioned; and if `body_db2` equals `body_oracle` under **whitespace normalization** (`_normalize_ws` collapses all whitespace runs to single spaces), `body_db2` is cleared to `""` so the card can render "Identical to Oracle" instead of duplicating the body. Otherwise both bodies are kept.

**Inputs -> outputs.** `reconcile_tables(oracle, db2) -> list[Table]`; `reconcile_plsql(oracle, db2) -> list[PlsqlObject]`.

**Dependencies.** internal: `model`; external: `re`, `dataclasses.replace`.

**Invoked / deployed.** Called by `run` after both dialects are parsed. `run` also imports `_looks_like_package_body` and `_normalize_ws` for its duplicate detection.

### `emit.py`
**Purpose.** Render a `Table`/`PlsqlObject` into an OKF `dbobject` markdown card, and a manifest index line. Everything sourced from DDL text (comments, types, bodies) is rendered **verbatim** - never fabricated or normalized.

**Key logic.**
- `card_id` -> `wms/db/tables/<NAME>` or `wms/db/plsql/<NAME>`.
- **Frontmatter** is emitted via `yaml.safe_dump` (the same library hive-serve's loader parses back with `yaml.safe_load`), so a comment containing `:` or other YAML-special characters is always quoted correctly rather than hand-rolled. `platform` lists dialects in canonical order (`oracle`, `db2`).
- **Table card** (`table_card`): a Columns markdown table (`Column | Oracle type | DB2 type | Null | Key | Description`), then Primary key / Foreign keys / Indexes / Sequences / Triggers sections. A `|` in any comment is escaped to `\|` by `_esc_cell` so it can't break a table row. A column missing from a dialect renders its type as `_MISSING_TYPE` (the em-dash literal `—`). FKs render `col → ref(ref_col)` with a `wms/db/tables/<ref>` cross-link, and `related`/`sources` frontmatter is derived from FKs and dialects.
- **PL/SQL card** (`plsql_card`): a Signature/spec fenced block, a Source (Oracle) block (`o.body_oracle`), and a Source (DB2) block that is either `o.body_db2` or the literal "Identical to Oracle." when `body_db2` was cleared by reconcile. `title`/`description` use only the header comment, never the raw signature/DDL text (search-field hygiene, since `find_db_objects` searches those fields).
- **Sources.** `_table_sources` uses `Table.source_files` when the runner set them, else synthesizes `<Dialect>/DBScripts/Product/<module>.sql` (correct for tables, whose file is named after the module). `_plsql_sources` likewise prefers `source_files`; its fallback (`.../PLSQL_Objects/<name>.sql`) is a best-effort guess only, since a PL/SQL file is named per file not per object - this is why the runner always sets `source_files` for real runs.
- `manifest_line` -> `{id, kind, module, product, title, description, tags}` per object.

**Inputs -> outputs.** `table_card(t)`/`plsql_card(o)` -> markdown string; `manifest_line(obj)` -> dict.

**Dependencies.** internal: `model`; external: `PyYAML`.

**Invoked / deployed.** Called by `run` when writing cards and building the manifest.

### `run.py`
**Purpose.** The end-to-end runner and the home of the verification gate. Walks the tree, parses both dialects, reconciles, gates, and writes cards + `manifest.jsonl` (+ `conflicts.log`).

**Key logic.**
- **Tree walk.** Per dialect it walks three locations: the non-recursive globs `Product/*.sql` (tables + inline PL/SQL) and `Product/PLSQL_Objects/*.sql` (PL/SQL units), plus a recursive walk of `Seed/Product/<module>/` - the base-schema catalogs (`*_Tables_PKs.sql`), which hold the bulk of the tables and are disjoint from the module files. Under `Seed/Product/` the per-table INSERT seed-data files (no object DDL) are filtered out. `Product/` module files come **first**, so the Product definition wins the keep-first dedup on any table declared in both trees. Everything else stays unwalked - the `Product/*.sql` glob is non-recursive (`Product/Seed/`, `Product/Archive/`, `Product/Upgrade/`, `Product/CreateSchema/`) and the Seed walk is scoped to `Seed/Product/` (so `Seed/Archive/`, `Seed/Merges/`, `Seed/Shared/` are never read). Files are sorted; `--limit-modules` caps files per dialect/kind for smoke runs. Each object's `module` is the filename stem and each object's `source_files` is the real repo-relative path(s).
- **Warning capture.** `_capture_warnings` is a context manager that attaches a temporary WARNING handler to a named logger, so the parsers' per-statement WARNINGs are collected per file (attributed as `"<repo-relative file>: <message>"`) without changing the parsers' return types (which the unit tests depend on). These accumulate into `unparsed`.
- **Two-source PL/SQL.** `_parse_dialect_tables` appends inline PL/SQL from module files, and `_parse_dialect_plsql` appends units from `PLSQL_Objects/`, into shared per-dialect accumulators; duplicate detection then runs once over the combined collection.
- **Reconcile + source union.** After both dialects, `reconcile_tables`/`reconcile_plsql` merge them, then each merged object's `source_files` is set via `_union_sources` (Oracle paths first, deduped).
- **Duplicate handling (non-fatal).** A same-dialect same-name duplicate is at worst "we card one of two near-identical definitions," not a drop of unique content - so it is **deduped (first kept), both files recorded, and a line appended to `conflicts.log`**, but the run still succeeds. Table duplicates compare structure via `_table_structure_key` (an order-insensitive frozenset of `(name, type_oracle, type_db2, not_null)` columns plus the PK set - tablespace/storage isn't parsed, so it never affects the key) and log `identical` or `differs in columns/pk`. PL/SQL duplicates are grouped by name in `_detect_plsql_duplicates`; a legitimate package spec/body pair (`_is_legit_package_pair`: all `package`, at most one spec and one body, using reconcile's own discriminator) is NOT flagged, everything else logs `identical`/`differs in body`. A cross-dialect Oracle/DB2 merge is never a duplicate.
- **The verification gate.** After writing all cards + manifest, `run` raises `RunError` if `unparsed` is non-empty - this is the one hard invariant, since an unparsed statement/unit is the only case that silently drops unique content. As a cheaper secondary check, it also raises if any kind's emitted-card count != its parsed-object count. The gate arithmetic is thus: `emitted == parsed` per kind, and `len(unparsed) == 0`. The run always completes the full walk first, so the `RunError` message can report exactly what failed.
- **Output.** Writes `out_dir/tables/<NAME>.md`, `out_dir/plsql/<NAME>.md`, `out_dir/manifest.jsonl`, and `out_dir/conflicts.log` (only when duplicates exist). Returns a `RunReport` (per-kind parsed/emitted counts, `unparsed`, `duplicates`).
- **CLI.** `main` uses argparse with `--src`, `--out`, and optional `--limit-modules`, then prints the report as JSON. The console entry point is `hivedbparse = hivedbparse.run:main`, and `python -m hivedbparse.run` works via `__main__`.

**Inputs -> outputs.** `run(src_root, out_dir, *, limit_modules=None) -> RunReport`; side effects are the written cards/manifest/conflicts.log.

**Dependencies.** internal: `emit`, `model`, `parse_aux`, `parse_plsql`, `parse_tables`, `reconcile`; external: `argparse`, `json`, `logging`, `pathlib`, `dataclasses`.

**Invoked / deployed.** The single entry point for the whole package; run once on the dev box.

## Deployment & runtime
This is a **one-time, deterministic, LLM-free** tool run by hand on the dev box against a checked-out Manhattan DDL tree - there is no `deploy/` directory and no service. It is invoked as:

```
cd tooling/hive-dbparse
uv run python -m hivedbparse.run --src <ManhDBDeploy_root> --out ../../concepts/wms/db
```

(Note: `main` takes the flags `--src`/`--out` (and optional `--limit-modules`); the deploy paths are `<root>/{Oracle,DB2}/DBScripts/Product/*.sql`, `.../Product/PLSQL_Objects/*.sql`, and `.../DBScripts/Seed/Product/<module>/**.sql`.) The only runtime dependency is `sqlglot` (plus `PyYAML` for frontmatter emission); no network, no model calls. It runs behind the **hard verification gate** so there is no partial corpus: any unparsed table statement or `CREATE OR REPLACE` unit fails the whole run, and every kind's emitted count must equal its parsed count. Same-dialect same-name duplicates are deduped (if identical) or logged to `conflicts.log` (if differing) but never fail the run. Re-run only when the source DDL changes.

Output: `tables/<NAME>.md` + `plsql/<NAME>.md` cards, `manifest.jsonl`, and (when duplicates exist) `conflicts.log`, all under `concepts/wms/db/`. These cards are served on demand by hive-serve behind `find_db_objects` and are deliberately kept out of `list_concepts`.

## Tests
Fixtures-only, fakes-free posture: the tests exercise the **real** `sqlglot` against small inline DDL strings and, for `run`, against a temporary `tmp_path` tree written per test (`Oracle/DBScripts/Product/...`, `DB2/...`) - no mocking of the parser, no real Manhattan DDL checked in. They cover each stage: table parsing (storage-tail trimming, constraint-state stripping, CTAS skip), aux attachment, PL/SQL boundary/verbatim slicing and the standalone-`/` rule, reconcile union/body-dedup, emit card/frontmatter/escaping, and the runner's gate (e.g. `test_gate_fails_on_unparsed_object` asserts `RunError` on broken DDL). Run with:

```
cd tooling/hive-dbparse && uv run pytest -q
```

Count: 101 test functions across `tests/test_parse_tables.py` (16), `test_parse_aux.py` (19), `test_parse_plsql.py` (20), `test_reconcile.py` (10), `test_emit.py` (16), and `test_run.py` (20).

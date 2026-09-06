# hive-dbparse

Schema DDL to cards. Package `hivedbparse`, CLI `hivedbparse`. Deterministic and model-free.

Narrative version: [database objects](../guides/database-objects.md).

## Running

```bash
hivedbparse --src <ddl-tree> --out <output-dir> [--limit-modules N]
```

| Option | Does |
|---|---|
| `--src` | root of the DDL tree |
| `--out` | where cards and the manifest go |
| `--limit-modules` | cap files per dialect and kind, for a smoke run |

## The flow

```
parse (per dialect)  ──►  reconcile  ──►  gate  ──►  emit
```

Oracle and DB2 are parsed independently, then unioned into one dialect-tagged model per object.
The gate runs before anything is written.

Handles `CREATE TABLE`, `COMMENT ON`, `ALTER`, `CREATE INDEX`, `CREATE SEQUENCE`, and
`CREATE [OR REPLACE]` routine units.

## Why deterministic

Every step is driven by a SQL tokenizer and AST plus exact character-slice arithmetic. The same
input always produces byte-identical cards, and routine bodies are copied verbatim rather than
summarised.

A schema is already structured. A model could only add the possibility of getting a column type
wrong, and a schema card that is subtly wrong is worse than no card, because it is believed.

## The verification gate

**No unparsed construct may be silently dropped.** If the parser meets something it does not
understand, the run fails and writes nothing.

This is inconvenient by design. A partial schema corpus answers "does this table have a status
column" with a confident "no" when the truth is that the parser choked on that file. A missing
corpus produces an error that someone fixes; a corpus with holes produces wrong answers that
someone believes.

An unparsed construct is a parser bug to fix, not a file to exclude.

## Modules

| Module | Purpose |
|---|---|
| `model.py` | the dataclasses carrying parsed state: `Column`, `Table`, `PlsqlObject` |
| `parse_tables.py` | `CREATE TABLE` to `Table` via AST, with token-level fallbacks for storage and constraint noise |
| `parse_aux.py` | attach comments, foreign keys, indexes and sequences onto existing tables |
| `parse_plsql.py` | slice routine units by tokenizer boundary detection; bodies captured verbatim |
| `reconcile.py` | union the two dialect runs into one dialect-tagged model per object |
| `emit.py` | render cards and manifest lines |
| `run.py` | walk, parse, reconcile, gate, write |

## Internals

Module-level detail, verified against the code on 2026-07-30.

### What the walk actually covers

Three locations per dialect, and the third is the one that is easy to miss:

| Location | Holds |
|---|---|
| `DBScripts/Product/*.sql` | module files, **non-recursive** |
| `DBScripts/Seed/Product/<module>/` | the base-schema catalogs, where the bulk of the classic tables are declared |
| `DBScripts/Product/PLSQL_Objects/*.sql` | dedicated PL/SQL units |

Subdirectories under `Product/` (`Seed/`, `Archive/`, `Upgrade/`, `CreateSchema/`) and the
non-`Product` `Seed/` subtrees (`Archive/`, `Merges/`, `Shared/`) are **never walked**. Under
`Seed/Product`, per-table INSERT seed-data files carrying no object DDL are skipped by content.

> **Pointing this at only `Product/*.sql` produces a corpus that looks complete.** The base-schema
> catalogs are disjoint from the module files, so omitting them drops thousands of tables while
> every gate passes: a gate that verifies completeness against its own input cannot tell you the
> input was incomplete.

`module` comes from the source filename stem. `source_files` records the actual path each object
was read from, which is what makes a PL/SQL card's `sources:` point at its real file rather than a
synthesised module name.

### The gate, precisely

**The gate is hard on exactly one thing: unparsed objects.** That is the only case that silently
drops unique content.

The run always finishes the full walk before raising, so the error can report exactly what did and
did not work. `parse_tables` and `parse_plsql` log a warning with a source snippet rather than
skipping quietly, including a `CREATE OR REPLACE` whose object-kind keyword matches no known
PL/SQL kind. Warnings are captured per file, so each is attributed to where it came from.

**Same-name duplicates within a dialect do not fail the run.** A duplicate is at worst two
near-identical definitions where one gets carded, which is not a drop of unique content. Each is
deduped keeping the first seen, **both** source files are recorded on the survivor, and a line
naming the object, the files, and whether they are identical or differ is appended to
`conflicts.log`. Visible, never silent, never fatal.

Two things are *not* logged as duplicates because they are legitimate merges: a cross-dialect match
of the same name, and a package spec paired with its body.

The emitted-equals-parsed count check is a **cheap consistency assertion, not the primary
protection**.

> **The gate counts; it does not diff.** A change that rewrites existing cards passes it cleanly.
> Require an additive-only git diff on any re-run.

### `parse_tables.py`

sqlglot with a dialect map. **sqlglot has no native DB2 dialect**, so DB2 DDL is parsed with the
generic ANSI dialect; the logical label is kept for tagging regardless of what parsed it.

Where sqlglot bails on physical-storage clauses (`TABLESPACE`, `STORAGE (...)`, `PCTFREE`), a
token-level **fragment fallback** extracts the parseable `CREATE TABLE` head by paren matching.
Oracle's inline `USING INDEX TABLESPACE` needs separate handling because it sits *inside* the
parens, where paren-matching cannot trim it.

### `parse_aux.py`, `parse_plsql.py`

`parse_aux` overlays the out-of-line facts: `COMMENT ON` kept **verbatim** as the human
description, foreign keys, indexes, sequences.

`parse_plsql` captures each unit's signature and **full body as a verbatim character slice**, so
nothing is paraphrased or normalised. Unit boundaries come from the tokenizer:

> **A `/` terminates a unit only when it stands alone on its line.** That is the SQL\*Plus
> terminator. Treating every `/` as a boundary truncates any body containing a division.

Units are captured from both the dedicated PL/SQL files and inline in the module files. Most
triggers and views live inline, so skipping inline capture drops a large fraction of the tier.

### `reconcile.py`

Matches objects across dialects by name. Oracle is the structural base; DB2 contributes `type_db2`
on matching columns. PL/SQL bodies are unioned by name with a **whitespace-normalised** body
comparison, so an identical body renders as "identical" rather than as two copies. Package spec and
body are merged into one unit.

### `emit.py`

One card and one `manifest.jsonl` line per object, with a **deterministic `card_id`**, so a re-run
over unchanged DDL produces byte-identical output and an empty diff. Frontmatter is written through
safe YAML.

## Tests

Fakes and DDL fixtures only. No database is needed, because the parser reads SQL text. Use
`uv run pytest --collect-only -q` in `tooling/hive-dbparse/` for the current inventory rather
than a count written down here.

## Output

One markdown card per object, plus `manifest.jsonl` recording what was parsed, plus `conflicts.log`
recording objects defined more than once across source files.

Cards land under `concepts/<product>/db/tables/` and `concepts/<product>/db/plsql/`. They are
excluded from the concept index and reached through `find_db_objects` or by id.

Foreign keys render as links to the referenced table's card, so the schema graph is navigable
rather than a flat listing.

## Re-running

Idempotent. Re-run when the schema changes and diff the output: because nothing was paraphrased,
the diff is exactly the schema change, which makes it a usable review artifact in a way a
model-generated diff never is.

There is no service and no deployment directory. This runs once, or when the schema changes.

## Naming the product

`--product` sets the card id prefix and the `product` facet, defaulting to the neutral `db`.

The value threads through everything rendered, not just the ids: foreign-key links, trigger links
and the facet. A schema parsed under the wrong product produces cards whose links point at ids that
do not exist, so set it explicitly.

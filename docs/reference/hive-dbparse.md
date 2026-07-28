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

## A known limitation

Card ids and the `product` facet are hardcoded to one product name in `emit.py`. Parsing a schema
for a differently-named product means editing that file.

Making it a parameter is tracked work. See
[known limitations](../concepts/principles.md#known-limitations).

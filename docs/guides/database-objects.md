# Database objects

`hive-dbparse` turns schema DDL into cards. No model is involved at any point.

```bash
cd tooling/hive-dbparse
uv run hivedbparse --src /path/to/ddl --out /path/to/output
```

Options: `--src` is the DDL tree root, `--out` is where cards and the manifest go, and
`--limit-modules` caps files per dialect and kind for a smoke run.

Oracle and DB2 dialects are supported. Parsing is done with a SQL AST parser, so what lands in a
card is what the DDL says.

## Why no model

A schema is already structured. A table has a name, columns with types, keys and constraints, and a
model adds nothing except the possibility of getting one of them wrong.

The consequence matters more than the reasoning. **A schema card is either exactly right or the
run failed.** There is no middle state where a column is subtly misdescribed, because nothing ever
paraphrased anything.

## The run fails rather than emitting a partial corpus

If the parser meets a construct it does not understand, the whole run fails. It does not skip the
file, log a warning and carry on.

This is worth defending, because it is inconvenient. A partial schema corpus is actively dangerous:
an agent asked "does this table have a status column" answers "no" with complete confidence when
the truth is that the parser choked on that file. A missing corpus produces an error, which someone
fixes. A corpus with holes produces wrong answers, which someone believes.

So an unparsed construct is a bug to fix in the parser, not a file to exclude.

## The on-demand tier

Database-object cards are **excluded from the concept index**. They do not appear in
`GET /concepts` or in `list_concepts`.

A real schema is large. In the corpus this feature was built for, it is over 7,000 objects against
roughly 1,000 concept cards, so including them would mean the index is 88% schema and a search for
a business concept returns table names.

They are reached through `find_db_objects` instead, which searches them directly, and resolved by
id like anything else:

```
GET /card/<product>/db/tables/ORDERS
GET /card/<product>/db/plsql/ORDER_TOTAL
```

The ids are path-derived, as with every card.

## What a schema card carries

Columns with types and nullability, primary and foreign keys, indexes, and for routines the
signature and dependencies. Foreign keys are rendered as links to the referenced table's card, so
the schema graph is navigable rather than a flat list.

## Re-running

The parse is idempotent and deterministic: the same DDL produces the same cards. Re-run it when the
schema changes, and diff the output. Because nothing was paraphrased, the diff is exactly the
schema change, which makes it a usable review artifact in a way an LLM-generated diff never is.

A manifest is written alongside the cards recording what was parsed, and a conflicts log records
duplicate object definitions across source files.

## A known limitation

Card ids and the `product` facet are currently hardcoded to one product name in
`hivedbparse/emit.py`. Parsing a schema for a differently-named product means editing that file.

Making it a parameter is tracked work. See
[known limitations](../concepts/principles.md#known-limitations).

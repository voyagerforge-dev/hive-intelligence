"""Attach comments, FKs, indexes and sequences to `Table` objects built by `parse_tables`.

Uses sqlglot's AST exclusively (tokenizer + parser) -- never regex -- to walk
`COMMENT ON TABLE/COLUMN`, `ALTER TABLE ... ADD ... FOREIGN KEY`,
`CREATE [UNIQUE] INDEX` and `CREATE SEQUENCE` statements and mutate the
already-parsed `Table`/`Column` objects in place. Statements that reference a
table not present in `tables` (and statements sqlglot cannot parse at all) are
skipped and logged -- never allowed to crash the run.
"""

from __future__ import annotations

import logging
import re

import sqlglot
from sqlglot import exp

from okfdbparse.model import Table
from okfdbparse.parse_tables import _sqlglot_dialect, _split_statements

logger = logging.getLogger(__name__)

# The only statement kinds `_apply_node` attaches: COMMENT ON, ALTER TABLE ...,
# CREATE [UNIQUE|BITMAP] INDEX, CREATE SEQUENCE. A statement whose first
# keyword (past leading whitespace/`--`/`/*...*/` noise) isn't one of these is
# skipped without a parse attempt -- crucial over the Seed catalogs, whose
# hundreds of thousands of PL/SQL-body fragments would otherwise each be
# parsed and warned about, dominating the run. Attachment is unchanged:
# `_apply_node` ignored those nodes anyway.
_AUX_STMT = re.compile(
    r"\s*(?:--[^\n]*\n\s*|/\*.*?\*/\s*)*"
    r"(?:COMMENT\b|ALTER\s+TABLE\b|CREATE\s+(?:UNIQUE\s+|BITMAP\s+)?INDEX\b|CREATE\s+SEQUENCE\b)",
    re.IGNORECASE | re.DOTALL,
)


def _is_aux_statement(stmt_text: str) -> bool:
    """True only for statements `_apply_node` can attach (see `_AUX_STMT`)."""
    return _AUX_STMT.match(stmt_text) is not None

# Suffixes/prefixes DDL authors commonly hang off a sequence name that derives
# from its owning table's name (e.g. `ORDER_LINE_SEQ`, `SEQ_ORDER_LINE`).
_SEQUENCE_AFFIXES = ("_SEQUENCE", "_SEQ", "SEQUENCE_", "SEQ_")


def _strip_sequence_affixes(name: str) -> str:
    stem = name.upper()
    for affix in _SEQUENCE_AFFIXES:
        if affix.endswith("_") and stem.startswith(affix):
            stem = stem[len(affix) :]
            break
        if affix.startswith("_") and stem.endswith(affix):
            stem = stem[: -len(affix)]
            break
    return stem.strip("_")


def _sequence_owner(tables: dict[str, Table], seq_name: str) -> Table | None:
    """Find the table that owns `seq_name` by a name-prefix heuristic.

    Strips common sequence affixes (`_SEQ`, `SEQ_`, ...) from the sequence
    name, then picks the table whose name is the longest exact/prefix match
    against the remaining stem. Returns `None` (an orphan sequence) when no
    table matches.
    """
    stem = _strip_sequence_affixes(seq_name)
    if not stem:
        return None

    best_table: Table | None = None
    best_len = -1
    for table_name, table in tables.items():
        upper = table_name.upper()
        matches = stem == upper or stem.startswith(upper + "_") or upper.startswith(stem)
        if matches and len(upper) > best_len:
            best_table = table
            best_len = len(upper)
    return best_table


def _comment_text(node: exp.Comment) -> str:
    expression = node.expression
    return expression.this if isinstance(expression, exp.Literal) else str(expression)


def _apply_comment(tables: dict[str, Table], node: exp.Comment) -> None:
    kind = (node.args.get("kind") or "").lower()
    text = _comment_text(node)
    target = node.this

    if kind == "table":
        table_name = target.name
        table = tables.get(table_name)
        if table is None:
            logger.warning("okfdbparse: COMMENT ON TABLE references unknown table %s", table_name)
            return
        table.comment = text
    elif kind == "column":
        table_name = target.table
        column_name = target.name
        table = tables.get(table_name)
        if table is None:
            logger.warning("okfdbparse: COMMENT ON COLUMN references unknown table %s", table_name)
            return
        column = next((c for c in table.columns if c.name == column_name), None)
        if column is None:
            logger.warning(
                "okfdbparse: COMMENT ON COLUMN references unknown column %s.%s",
                table_name,
                column_name,
            )
            return
        column.comment = text
    else:
        logger.warning("okfdbparse: unrecognized COMMENT kind %r", kind)


def _apply_alter_table(tables: dict[str, Table], node: exp.Alter) -> None:
    if (node.args.get("kind") or "").upper() != "TABLE":
        return

    table_name = node.this.name
    table = tables.get(table_name)

    for fk in node.find_all(exp.ForeignKey):
        reference = fk.args.get("reference")
        if reference is None:
            continue
        ref_table_name = reference.this.this.name
        ref_columns = reference.this.expressions

        if table is None:
            logger.warning(
                "okfdbparse: ALTER TABLE ADD FOREIGN KEY references unknown table %s", table_name
            )
            continue

        for col, ref_col in zip(fk.expressions, ref_columns):
            table.fks.append((col.name, ref_table_name, ref_col.name))


def _apply_create_index(tables: dict[str, Table], node: exp.Create) -> None:
    index = node.this
    table_name = index.args["table"].name
    table = tables.get(table_name)
    if table is None:
        logger.warning("okfdbparse: CREATE INDEX references unknown table %s", table_name)
        return

    index_name = index.this.name
    params = index.args.get("params")
    columns: list[str] = []
    if params is not None:
        for col_expr in params.args.get("columns") or []:
            column = col_expr.this if isinstance(col_expr, exp.Ordered) else col_expr
            columns.append(column.name)

    unique = bool(node.args.get("unique"))
    table.indexes.append((index_name, columns, unique))


def _apply_create_sequence(tables: dict[str, Table], node: exp.Create) -> None:
    seq_name = node.this.name
    owner = _sequence_owner(tables, seq_name)
    if owner is None:
        logger.warning("okfdbparse: CREATE SEQUENCE %s has no clear owning table", seq_name)
        return
    owner.sequences.append(seq_name)


def _apply_node(tables: dict[str, Table], node: exp.Expression) -> None:
    if isinstance(node, exp.Comment):
        _apply_comment(tables, node)
    elif isinstance(node, exp.Alter):
        _apply_alter_table(tables, node)
    elif isinstance(node, exp.Create):
        kind = (node.args.get("kind") or "").upper()
        if kind == "INDEX":
            _apply_create_index(tables, node)
        elif kind == "SEQUENCE":
            _apply_create_sequence(tables, node)
    elif isinstance(node, exp.Command):
        logger.warning("okfdbparse: aux statement degraded to Command, skipping: %.80s", node.sql())
    # else: statement type we don't attach (e.g. GRANT, CREATE TABLE) -- ignore


def apply_aux(tables: dict[str, Table], sql: str, dialect: str) -> None:
    """Attach comments/FKs/indexes/sequences parsed from `sql` onto `tables`, in place.

    `dialect` is the logical `"oracle"`/`"db2"` label from `parse_tables`; it is
    mapped to the sqlglot dialect via the shared `_sqlglot_dialect` helper
    (sqlglot has no native "db2" dialect). Statements are split on top-level
    semicolons with the dialect's own tokenizer (reusing `_split_statements`
    from `parse_tables`) and parsed one at a time so that one unparseable or
    unrelated statement never aborts the rest of the file.
    """
    sqlglot_dialect = _sqlglot_dialect(dialect)

    for stmt_text in _split_statements(sql, sqlglot_dialect):
        if not _is_aux_statement(stmt_text):
            continue
        try:
            node = sqlglot.parse_one(stmt_text, read=sqlglot_dialect)
        except Exception:  # noqa: BLE001 -- skip unparseable aux statements, never crash
            logger.warning("okfdbparse: could not parse aux statement: %.80s", stmt_text.strip())
            continue
        if node is not None:
            _apply_node(tables, node)

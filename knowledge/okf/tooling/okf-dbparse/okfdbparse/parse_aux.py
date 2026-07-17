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
from okfdbparse.parse_tables import (
    _extract_create_table_fragment,
    _sqlglot_dialect,
    _split_statements,
    _strip_constraint_state,
    _strip_using_index_clause,
)

# Hard failures -- DDL we should have understood but couldn't. The runner
# captures this logger into the verification gate: an aux statement that
# reaches `_apply_node` carrying attachable content and fails to parse is a
# SILENT DROP (a lost index/sequence/FK/comment), so it must fail the run.
logger = logging.getLogger(__name__)

# Soft, non-fatal misses -- the statement parsed fine, but its target isn't in
# the carded corpus (a comment/FK/index on a table we don't walk) or no owning
# table could be resolved (an orphan sequence). These are a consequence of
# corpus SCOPE, not a parser gap, so they're reported (`unattached.log`) rather
# than gated. Deliberately a SIBLING logger of `logger`, not a child: a handler
# on `okfdbparse.parse_aux` would otherwise capture these too via propagation.
unattached_logger = logging.getLogger("okfdbparse.aux_unattached")

# The statement kinds `_apply_node` actually attaches. Narrow ON PURPOSE: every
# statement passing this filter carries content we attach, so a parse failure on
# one is a real drop the gate can fail honestly. Everything else (CREATE TABLE,
# PL/SQL bodies, INSERT seed data, `ALTER TABLE ... MOVE TABLESPACE`, ...) is
# skipped without a parse attempt -- crucial over the Seed catalogs, whose
# hundreds of thousands of PL/SQL-body fragments would otherwise each be parsed.
_AUX_HEAD = re.compile(
    r"\s*(?:--[^\n]*\n\s*|/\*.*?\*/\s*)*"
    r"(COMMENT\b|ALTER\s+TABLE\b|CREATE\s+(?:UNIQUE\s+|BITMAP\s+)?INDEX\b|CREATE\s+SEQUENCE\b)",
    re.IGNORECASE | re.DOTALL,
)
# Only an ADD of a foreign key carries columns + references we attach. DB2's
# `ALTER TABLE t ALTER FOREIGN KEY fk NOT ENFORCED` merely toggles an existing
# FK's enforcement -- no definition to attach, so it must NOT reach the gate.
_ADD_FOREIGN_KEY = re.compile(r"\bADD\b[^;]*?\bFOREIGN\s+KEY\b", re.IGNORECASE | re.DOTALL)

# sqlglot's Oracle grammar rejects a schema-qualified INDEX NAME
# (`CREATE INDEX session.idx1 ON session.t (...)` degrades to Command), though
# an unqualified index name on a schema-qualified TABLE parses fine. The index's
# own schema is cosmetic here (we attach by table, and don't model index schema),
# so drop just the `<schema>.` before the index name, leaving the ON-table ref.
_INDEX_NAME_SCHEMA = re.compile(
    r"(\bINDEX\s+)(?:\"?[\w$]+\"?\s*\.\s*)(\"?[\w$]+\"?\s+ON\b)", re.IGNORECASE
)


def _is_aux_statement(stmt_text: str) -> bool:
    """True only for statements `_apply_node` can attach (see `_AUX_HEAD`).

    An `ALTER TABLE` only qualifies when it adds a FOREIGN KEY -- every other
    alter (`MOVE TABLESPACE`, `ADD PARTITION`, `ENABLE CONSTRAINT`, ...) carries
    nothing this module models, so admitting it would make the gate fail on
    statements that were never a drop.
    """
    m = _AUX_HEAD.match(stmt_text)
    if m is None:
        return False
    if m.group(1).upper().startswith("ALTER"):
        return _ADD_FOREIGN_KEY.search(stmt_text) is not None
    return True


def _parse_aux_statement(stmt_text: str, sqlglot_dialect: str | None) -> exp.Expression | None:
    """Parse one aux statement, trimming a physical-storage tail if needed.

    Real Oracle DDL trails `CREATE INDEX x ON t (cols)` with storage clauses
    (`TABLESPACE ... PCTFREE ... INITRANS ...`) that sqlglot can't model, so it
    degrades the WHOLE statement to `exp.Command` -- and `_apply_node` then
    skips it, silently losing the index. This retries against the bare
    `CREATE ... (...)` fragment (the same token-level paren-slice trick
    `parse_tables` uses for `CREATE TABLE`). Returns `None` when the statement
    is genuinely unparseable.
    """
    # Same physical-noise cleaners `parse_tables` runs: a trailing constraint
    # state (`... FOREIGN KEY (A) REFERENCES P (B) ENABLE NOVALIDATE;`) or a
    # `USING INDEX TABLESPACE ...` clause degrades the whole ALTER/CREATE to an
    # opaque `Command`; stripping them lets the FK/index parse cleanly.
    stmt_text = _strip_using_index_clause(
        _strip_constraint_state(stmt_text, sqlglot_dialect), sqlglot_dialect
    )
    stmt_text = _INDEX_NAME_SCHEMA.sub(r"\1\2", stmt_text)
    try:
        node = sqlglot.parse_one(stmt_text, read=sqlglot_dialect)
    except Exception:  # noqa: BLE001 -- fall through to the fragment retry
        node = None

    if node is not None and not isinstance(node, exp.Command):
        return node

    fragment = _extract_create_table_fragment(stmt_text, sqlglot_dialect)
    if fragment is not None:
        try:
            retry = sqlglot.parse_one(fragment, read=sqlglot_dialect)
        except Exception:  # noqa: BLE001
            retry = None
        if retry is not None and not isinstance(retry, exp.Command):
            return retry
    return node

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
            unattached_logger.warning("okfdbparse: COMMENT ON TABLE references unknown table %s", table_name)
            return
        table.comment = text
    elif kind == "column":
        table_name = target.table
        column_name = target.name
        table = tables.get(table_name)
        if table is None:
            unattached_logger.warning("okfdbparse: COMMENT ON COLUMN references unknown table %s", table_name)
            return
        column = next((c for c in table.columns if c.name == column_name), None)
        if column is None:
            unattached_logger.warning(
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
            unattached_logger.warning(
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
        unattached_logger.warning("okfdbparse: CREATE INDEX references unknown table %s", table_name)
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
        unattached_logger.warning("okfdbparse: CREATE SEQUENCE %s has no clear owning table", seq_name)
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
        node = _parse_aux_statement(stmt_text, sqlglot_dialect)
        # Everything reaching here carries content we attach (`_is_aux_statement`
        # is narrow by design), so failing to parse it -- or only getting an
        # opaque `Command` back even after the storage-tail retry -- means we are
        # DROPPING a real index/sequence/FK/comment. That is exactly the silent
        # loss the verification gate exists to catch, so warn on `logger` (which
        # the runner routes into the gate) rather than skipping quietly.
        if node is None or isinstance(node, exp.Command):
            logger.warning("okfdbparse: could not parse aux statement: %.80s", stmt_text.strip())
            continue
        _apply_node(tables, node)

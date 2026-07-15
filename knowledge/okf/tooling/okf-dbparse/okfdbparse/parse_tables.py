"""Parse `CREATE TABLE` statements from WMOS Oracle/DB2 DDL into `Table` objects.

Uses sqlglot's AST exclusively (tokenizer + parser) -- never regex -- so that
messy real-world DDL (nested type parens like NUMBER(20,0), quoted identifiers,
inline `--` comments, multi-line statements) is handled exactly.
"""

from __future__ import annotations

import logging

import sqlglot
from sqlglot import exp
from sqlglot.dialects.dialect import Dialect
from sqlglot.tokens import TokenType

from okfdbparse.model import Column, Table

logger = logging.getLogger(__name__)


def _split_statements(sql: str, dialect: str) -> list[str]:
    """Split `sql` into raw per-statement text slices on top-level semicolons.

    Uses the dialect's own tokenizer (comment/string aware -- a `;` inside a
    quoted string or comment is never mistaken for a separator), mirroring
    the chunking sqlglot's own parser does internally. Returns exact
    substrings of the original `sql`, never reconstructed/regenerated text.
    """
    tokenizer = Dialect.get_or_raise(dialect).tokenizer_class()
    tokens = tokenizer.tokenize(sql)

    statements: list[str] = []
    chunk: list = []
    for token in tokens:
        if token.token_type == TokenType.SEMICOLON:
            if chunk:
                statements.append(sql[chunk[0].start : chunk[-1].end + 1])
                chunk = []
        else:
            chunk.append(token)
    if chunk:
        statements.append(sql[chunk[0].start : chunk[-1].end + 1])
    return statements


def _extract_create_table_fragment(text: str, dialect: str) -> str | None:
    """Isolate a bare `CREATE TABLE name (...)` fragment from `text`.

    Real Oracle/DB2 DDL often trails the column-list with dialect-specific
    physical-storage clauses (`TABLESPACE ...`, `STORAGE (...)`, `PCTFREE ...`)
    that sqlglot's oracle/db2 dialects don't model and that fall outside the
    `Table` object model anyway. When sqlglot can't parse the whole statement
    because of such a tail, this trims it by finding the column-list's
    matching close-paren via token-level paren-depth counting (comment/string
    safe, nesting safe for types like NUMBER(20,0)) and slicing the original
    text -- never regex, never hand-parsing the column list itself.
    """
    tokenizer = Dialect.get_or_raise(dialect).tokenizer_class()
    tokens = tokenizer.tokenize(text)
    if len(tokens) < 3 or tokens[0].token_type != TokenType.CREATE:
        return None

    open_idx = next((i for i, tok in enumerate(tokens) if tok.token_type == TokenType.L_PAREN), None)
    if open_idx is None:
        return None

    depth = 0
    close_idx = None
    for i in range(open_idx, len(tokens)):
        if tokens[i].token_type == TokenType.L_PAREN:
            depth += 1
        elif tokens[i].token_type == TokenType.R_PAREN:
            depth -= 1
            if depth == 0:
                close_idx = i
                break
    if close_idx is None:
        return None

    return text[tokens[0].start : tokens[close_idx].end + 1]


def _find_create_table(expr: exp.Expr) -> exp.Create | None:
    for create in expr.find_all(exp.Create):
        if create.args.get("kind") == "TABLE" and isinstance(create.this, exp.Schema):
            return create
    return None


def _build_table(create: exp.Create, dialect: str) -> Table:
    schema = create.this
    name = schema.this.name

    table = Table(name=name, module="", dialects={dialect})

    for col_def in create.find_all(exp.ColumnDef):
        not_null = any(
            isinstance(constraint.kind, exp.NotNullColumnConstraint)
            for constraint in col_def.constraints
        )
        col_type = col_def.args.get("kind")
        type_sql = col_type.sql(dialect=dialect) if col_type is not None else None

        column = Column(name=col_def.name, not_null=not_null)
        if dialect == "db2":
            column.type_db2 = type_sql
        else:
            column.type_oracle = type_sql
        table.columns.append(column)

        for constraint in col_def.constraints:
            if isinstance(constraint.kind, exp.PrimaryKeyColumnConstraint):
                table.pk.append(col_def.name)

    for pk in create.find_all(exp.PrimaryKey):
        for pk_col in pk.args.get("expressions", []):
            col_name = pk_col.name
            if col_name not in table.pk:
                table.pk.append(col_name)

    return table


def parse_tables(sql: str, dialect: str) -> dict[str, Table]:
    """Parse all `CREATE TABLE` statements in `sql` into `{table_name: Table}`.

    `dialect` is `"oracle"` or `"db2"`. Sets `Table.dialects = {dialect}` and
    the per-dialect column type (`type_oracle`/`type_db2`). `Table.module` is
    left `""` -- the runner sets it from the source filename.
    """
    tables: dict[str, Table] = {}

    for stmt_text in _split_statements(sql, dialect):
        create: exp.Create | None = None

        try:
            parsed = sqlglot.parse_one(stmt_text, read=dialect)
        except Exception:  # noqa: BLE001 -- fall through to the fragment fallback below
            parsed = None

        if parsed is not None:
            create = _find_create_table(parsed)

        if create is None:
            fragment = _extract_create_table_fragment(stmt_text, dialect)
            if fragment is not None:
                try:
                    parsed = sqlglot.parse_one(fragment, read=dialect)
                except Exception:  # noqa: BLE001
                    parsed = None
                if parsed is not None:
                    create = _find_create_table(parsed)

        if create is None:
            head = stmt_text.strip().upper()
            if head.startswith("CREATE") and "TABLE" in head[:40]:
                logger.warning(
                    "okfdbparse: could not parse CREATE TABLE statement: %.80s", stmt_text.strip()
                )
            continue

        table = _build_table(create, dialect)
        tables[table.name] = table

    return tables

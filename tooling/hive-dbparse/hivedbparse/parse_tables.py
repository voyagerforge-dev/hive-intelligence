"""Parse `CREATE TABLE` statements from Oracle and DB2 DDL into `Table` objects.

Uses sqlglot's AST exclusively (tokenizer + parser) -- never regex -- so that
messy real-world DDL (nested type parens like NUMBER(20,0), quoted identifiers,
inline `--` comments, multi-line statements) is handled exactly.
"""

from __future__ import annotations

import logging
import re

import sqlglot
from sqlglot import exp
from sqlglot.dialects.dialect import Dialect
from sqlglot.tokens import TokenType

from hivedbparse.model import Column, Table

logger = logging.getLogger(__name__)

# Map our *logical* dialect labels ("oracle"/"db2") to a sqlglot dialect that
# actually exists. sqlglot 30.x has NO native "db2" dialect, so we parse DB2 DDL
# with the generic (ANSI) dialect (`None`) -- DB2's `CREATE TABLE` grammar is close
# to ANSI, and the token-based fragment fallback below covers the DB2-specific tail
# clauses (e.g. `IN <tablespace>`) that the AST can't model. The logical label is
# kept for tagging (`type_db2`, `Table.dialects`) regardless of the parse dialect.
_SQLGLOT_DIALECT: dict[str, str | None] = {
    "oracle": "oracle",
    "db2": None,
}


def _sqlglot_dialect(dialect: str) -> str | None:
    """Resolve a logical dialect label to a sqlglot dialect sqlglot supports."""
    try:
        return _SQLGLOT_DIALECT[dialect]
    except KeyError:
        raise ValueError(
            f"hivedbparse: unsupported logical dialect {dialect!r} (expected 'oracle' or 'db2')"
        ) from None


def _split_statements(sql: str, dialect: str | None) -> list[str]:
    """Split `sql` into raw per-statement text slices on top-level semicolons.

    Uses the dialect's own tokenizer (comment/string aware -- a `;` inside a
    quoted string or comment is never mistaken for a separator), mirroring
    the chunking sqlglot's own parser does internally. Returns exact
    substrings of the original `sql`, never reconstructed/regenerated text.

    NB: only `;` terminates. DB2 CLP scripts also use `!`, but `!` cannot be
    treated as a separator here -- it occurs mid-statement in string literals
    (`'... short !'`) and operators, and splitting on it corrupts DB2 CREATE
    TABLEs. `!`-terminated DB2 sequence files are handled instead by
    `parse_aux` extracting sequence names from the whole text (`_SEQUENCE_DECL`).
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


def _extract_create_table_fragment(text: str, dialect: str | None) -> str | None:
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

    open_idx = next(
        (i for i, tok in enumerate(tokens) if tok.token_type == TokenType.L_PAREN), None
    )
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


# Oracle constraint-state suffixes (appended by the DB export tool after a
# column's `NOT NULL` or after a table-level constraint's closing `)`) that
# sqlglot's oracle/generic grammars don't model at all -- e.g.
# `"X" NUMBER(9,0) NOT NULL ENABLE,` or
# `CONSTRAINT pk PRIMARY KEY (X) ENABLE`. They carry no information our
# `Column`/`Table` model captures (nullability already comes from `NOT NULL`
# itself), so they're pure noise for us and safe to drop.
_CONSTRAINT_STATE_KEYWORDS = {"ENABLE", "DISABLE", "VALIDATE", "NOVALIDATE"}

# Token types that can legally follow a constraint-state keyword in this
# corpus: a comma (another column/constraint follows), the table's own closing
# paren, or a semicolon (end of a standalone `ALTER TABLE ... ADD CONSTRAINT
# ... ENABLE;` statement -- the shape `apply_aux` cleans before parsing FKs). A
# *real* identifier can never be followed directly by one of these (every
# column needs a type, every constraint needs its clause) -- which is what lets
# this be recognized without any preceding-context check.
_STATE_FOLLOWER_TYPES = {TokenType.COMMA, TokenType.R_PAREN, TokenType.SEMICOLON}

# DB2's bare two-word "special register" default values (`CURRENT TIMESTAMP`/
# `CURRENT DATE`/`CURRENT TIME`, no underscore, no parens) that sqlglot's
# generic grammar (used to parse the DB2 logical dialect) only recognizes in
# their underscored form (`CURRENT_TIMESTAMP`/...). Real example:
# `LAST_UPDATED_DTTM TIMESTAMP DEFAULT CURRENT TIMESTAMP NOT NULL`.
_CURRENT_REGISTER_TYPES = {TokenType.TIMESTAMP, TokenType.DATE, TokenType.TIME}


def _is_constraint_state_token(tok) -> bool:
    return tok.token_type == TokenType.VAR and tok.text.upper() in _CONSTRAINT_STATE_KEYWORDS


def _strip_constraint_state(text: str, dialect: str | None) -> str:
    """Remove trailing Oracle constraint-state keywords (`ENABLE`/`DISABLE`/
    `VALIDATE`/`NOVALIDATE`) from `text`. Token-driven (never regex): a match
    is a bare `VAR` token whose text is one of the keywords AND whose very
    next token is a comma, the table's closing paren, or another
    constraint-state keyword (so a chain like `ENABLE VALIDATE` is fully
    stripped) -- never just "follows NOT NULL", so this also covers
    table-level `CONSTRAINT ... PRIMARY KEY (...) ENABLE`.
    """
    tokenizer = Dialect.get_or_raise(dialect).tokenizer_class()
    tokens = tokenizer.tokenize(text)

    drop: list[tuple[int, int]] = []
    for i, tok in enumerate(tokens):
        if not _is_constraint_state_token(tok):
            continue
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        is_follower = nxt is None or nxt.token_type in _STATE_FOLLOWER_TYPES
        if is_follower or _is_constraint_state_token(nxt):
            drop.append((tok.start, tok.end + 1))

    if not drop:
        return text

    out: list[str] = []
    cursor = 0
    for start, end in drop:
        out.append(text[cursor:start])
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


def _strip_using_index_clause(text: str, dialect: str | None) -> str:
    """Remove Oracle's `USING INDEX [TABLESPACE ...]`/inline index-storage
    clause that trails a *table-level* constraint definition INSIDE the
    column-list parens -- e.g.
    `CONSTRAINT pk PRIMARY KEY (X) USING INDEX TABLESPACE T`. Because it sits
    inside the parens, the paren-matching fragment fallback can't trim it, so
    sqlglot rejects the whole statement.

    Token-driven: for each `USING` token immediately followed by `INDEX`, drop
    the run from `USING` up to (but not including) the next `,` or `)` at the
    same-or-shallower paren depth as the `USING` token -- so an inline index
    spec that itself contains parens/commas is skipped whole, and the
    constraint's own list stays intact.
    """
    tokenizer = Dialect.get_or_raise(dialect).tokenizer_class()
    tokens = tokenizer.tokenize(text)

    drop: list[tuple[int, int]] = []
    n = len(tokens)
    for i, tok in enumerate(tokens):
        if not (
            tok.token_type == TokenType.USING
            and i + 1 < n
            and tokens[i + 1].token_type == TokenType.INDEX
        ):
            continue
        depth = 0
        end = tokens[-1].end + 1  # default: to end of text (clause runs to the close)
        for j in range(i + 1, n):
            tt = tokens[j].token_type
            if tt == TokenType.L_PAREN:
                depth += 1
            elif tt == TokenType.R_PAREN:
                if depth == 0:
                    end = tokens[j].start
                    break
                depth -= 1
            elif tt == TokenType.COMMA and depth == 0:
                end = tokens[j].start
                break
        drop.append((tok.start, end))

    if not drop:
        return text

    out: list[str] = []
    cursor = 0
    for start, end in drop:
        out.append(text[cursor:start])
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


def _normalize_current_registers(text: str, dialect: str | None) -> str:
    """Rewrite DB2's bare `CURRENT TIMESTAMP`/`CURRENT DATE`/`CURRENT TIME`
    special registers into their underscored form (`CURRENT_TIMESTAMP`/...)
    that sqlglot's generic grammar accepts. Token-driven: matches a bare `VAR`
    token whose text is `CURRENT` immediately followed by one of the
    TIMESTAMP/DATE/TIME keyword tokens, and splices the whitespace between
    them into a single `_` (a quoted `"CURRENT"` identifier tokenizes as
    `IDENTIFIER`, not `VAR`, so a genuinely-named column is never touched).
    """
    tokenizer = Dialect.get_or_raise(dialect).tokenizer_class()
    tokens = tokenizer.tokenize(text)

    splices: list[tuple[int, int]] = []  # (gap_start, gap_end) to replace with "_"
    for i, tok in enumerate(tokens):
        if not (tok.token_type == TokenType.VAR and tok.text.upper() == "CURRENT"):
            continue
        if i + 1 >= len(tokens):
            continue
        nxt = tokens[i + 1]
        if nxt.token_type in _CURRENT_REGISTER_TYPES:
            splices.append((tok.end + 1, nxt.start))

    if not splices:
        return text

    out: list[str] = []
    cursor = 0
    for gap_start, gap_end in splices:
        out.append(text[cursor:gap_start])
        out.append("_")
        cursor = gap_end
    out.append(text[cursor:])
    return "".join(out)


# An inline `GENERATED [ALWAYS | BY DEFAULT [ON NULL]] AS IDENTITY <options>`
# column clause, e.g. `NUMBER GENERATED ALWAYS AS IDENTITY MINVALUE 1 MAXVALUE
# 9999... INCREMENT BY 1 START WITH 1 CACHE 20 NOORDER NOCYCLE`. sqlglot rejects
# the fully-specified Oracle form; we don't model identity/default, so it's
# stripped back to the bare type. Only the IDENTITY keyword and its option
# tokens (a parenthesized group, or a run of MINVALUE/INCREMENT/CACHE/... and
# numbers) are consumed -- the match STOPS at the next column constraint, so a
# trailing `NOT NULL` (identity columns are NOT NULL) is preserved.
_IDENTITY_CLAUSE = re.compile(
    r"\bGENERATED\s+(?:ALWAYS|BY\s+DEFAULT(?:\s+ON\s+NULL)?)\s+AS\s+IDENTITY"
    r"(?:\s*\([^)]*\))?"
    r"(?:\s+(?:MINVALUE|MAXVALUE|INCREMENT|BY|START|WITH|CACHE|NOCACHE|"
    r"CYCLE|NOCYCLE|ORDER|NOORDER|\d+))*",
    re.IGNORECASE,
)
_LONG_RAW = re.compile(r"\bLONG\s+RAW\b", re.IGNORECASE)
_LONG = re.compile(r"\bLONG\b(?!\s+RAW)", re.IGNORECASE)


def _strip_identity_clause(text: str) -> str:
    """Remove an inline identity-column clause (see `_IDENTITY_CLAUSE`) so the
    column parses as its bare type. Identity/default aren't modelled."""
    return _IDENTITY_CLAUSE.sub("", text)


def _map_legacy_long_types(text: str) -> str:
    """Map Oracle's deprecated `LONG RAW`/`LONG` LOB types (which sqlglot cannot
    parse) to the modern equivalents `BLOB`/`CLOB` so the column parses. Only
    these two legacy types are touched; every other type passes through."""
    return _LONG.sub("CLOB", _LONG_RAW.sub("BLOB", text))


_TABLE_MODIFIER_VARS = {"GLOBAL", "PRIVATE", "SHARED"}


def _looks_like_create_table(stmt_text: str, dialect: str | None) -> bool:
    """True when `stmt_text` is a genuine (if unparseable) `CREATE TABLE`
    attempt -- used only to decide whether a parse failure deserves a WARNING
    (a real CREATE TABLE we choked on) vs. silence (some other `CREATE`
    statement -- SEQUENCE, TYPE, MATERIALIZED VIEW, ... -- that was never a
    table and mustn't be flagged just because the substring "TABLE" appears
    later in the text, e.g. inside `TABLESPACE` or Oracle's `AS TABLE OF`
    nested-table TYPE syntax).

    Token-driven: the first token must be `CREATE`, and the first
    non-modifier token after it (skipping `GLOBAL`/`PRIVATE`/`SHARED`/
    `TEMPORARY` -- Oracle's temporary-table modifiers) must be the literal
    `TABLE` keyword token.
    """
    tokenizer = Dialect.get_or_raise(dialect).tokenizer_class()
    tokens = tokenizer.tokenize(stmt_text)
    if not tokens or tokens[0].token_type != TokenType.CREATE:
        return False

    i = 1
    n = len(tokens)
    while i < n and (
        tokens[i].token_type == TokenType.TEMPORARY
        or (
            tokens[i].token_type == TokenType.VAR
            and tokens[i].text.upper() in _TABLE_MODIFIER_VARS
        )
    ):
        i += 1
    return i < n and tokens[i].token_type == TokenType.TABLE


def _find_create_table(expr: exp.Expr) -> exp.Create | None:
    for create in expr.find_all(exp.Create):
        if create.args.get("kind") == "TABLE" and isinstance(create.this, exp.Schema):
            return create
    return None


def _is_ctas(expr: exp.Expr) -> bool:
    """True when `expr` holds a `CREATE TABLE ... AS SELECT` (any dialect
    variant, including `CREATE GLOBAL TEMPORARY TABLE ... AS SELECT`): kind
    `TABLE`, but `this` is a bare `exp.Table` (no column list -- sqlglot only
    builds an `exp.Schema` when an explicit column list is present) with a
    query `expression`. A CTAS has no column list to card -- see module
    docstring's known-skip class.
    """
    for create in expr.find_all(exp.Create):
        if (
            create.args.get("kind") == "TABLE"
            and isinstance(create.this, exp.Table)
            and create.args.get("expression") is not None
        ):
            return True
    return False


def _build_table(create: exp.Create, dialect: str, sqlglot_dialect: str | None) -> Table:
    schema = create.this
    name = schema.this.name

    table = Table(name=name, module="", dialects={dialect})

    for col_def in create.find_all(exp.ColumnDef):
        not_null = any(
            isinstance(constraint.kind, exp.NotNullColumnConstraint)
            for constraint in col_def.constraints
        )
        col_type = col_def.args.get("kind")
        type_sql = col_type.sql(dialect=sqlglot_dialect) if col_type is not None else None

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

    `dialect` is the *logical* label used for tagging; sqlglot parses with the
    dialect `_sqlglot_dialect` maps it to (DB2 -> generic, since sqlglot has no
    native db2 dialect).
    """
    sqlglot_dialect = _sqlglot_dialect(dialect)
    tables: dict[str, Table] = {}

    for stmt_text in _split_statements(sql, sqlglot_dialect):
        create: exp.Create | None = None
        ctas = False

        # Clean up real-corpus noise the AST grammars don't model *before*
        # any parse attempt -- both the direct attempt below and the
        # fragment-fallback text derived from it benefit.
        cleaned_text = _strip_constraint_state(stmt_text, sqlglot_dialect)
        cleaned_text = _strip_using_index_clause(cleaned_text, sqlglot_dialect)
        cleaned_text = _normalize_current_registers(cleaned_text, sqlglot_dialect)
        cleaned_text = _strip_identity_clause(cleaned_text)
        cleaned_text = _map_legacy_long_types(cleaned_text)

        try:
            parsed = sqlglot.parse_one(cleaned_text, read=sqlglot_dialect)
        except Exception:  # noqa: BLE001 -- fall through to the fragment fallback below
            parsed = None

        if parsed is not None:
            create = _find_create_table(parsed)
            if create is None and _is_ctas(parsed):
                ctas = True

        if create is None and not ctas:
            fragment = _extract_create_table_fragment(cleaned_text, sqlglot_dialect)
            if fragment is not None:
                try:
                    parsed = sqlglot.parse_one(fragment, read=sqlglot_dialect)
                except Exception:  # noqa: BLE001
                    parsed = None
                if parsed is not None:
                    create = _find_create_table(parsed)
                    if create is None and _is_ctas(parsed):
                        ctas = True

        if ctas:
            # Known skip (class 3): a CTAS has no column list to card.
            logger.info(
                "hivedbparse: skipping CTAS (CREATE TABLE ... AS SELECT, no column "
                "list to card): %.80s",
                stmt_text.strip(),
            )
            continue

        if create is None:
            if _looks_like_create_table(stmt_text, sqlglot_dialect):
                logger.warning(
                    "hivedbparse: could not parse CREATE TABLE statement: %.80s", stmt_text.strip()
                )
            continue

        table = _build_table(create, dialect, sqlglot_dialect)
        tables[table.name] = table

    return tables

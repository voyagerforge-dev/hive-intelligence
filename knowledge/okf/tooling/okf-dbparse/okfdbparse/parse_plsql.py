"""Split `CREATE OR REPLACE` PL/SQL units from WMOS Oracle/DB2 source into `PlsqlObject`s.

PL/SQL package/procedure/function/trigger/view bodies are NOT standard SQL --
sqlglot's AST parser doesn't (and shouldn't) model their internals (`BEGIN...END`
blocks, `%TYPE` anchors, cursors, exception handlers, ...). This module never
hands a PL/SQL body to `sqlglot.parse_one`; it only uses the dialect's own
*tokenizer* (comment/string aware, so an inline `--` comment or a `;` inside a
quoted string literal is never mistaken for a unit boundary) to find where each
top-level `CREATE OR REPLACE ...` unit starts and ends, then slices the
*original* source text between those two character offsets. The body is
therefore captured byte-for-byte verbatim -- never reconstructed/regenerated
from tokens, which would lose the author's formatting.
"""

from __future__ import annotations

import logging

from sqlglot.dialects.dialect import Dialect
from sqlglot.tokens import Token, TokenType

from okfdbparse.model import PlsqlObject
from okfdbparse.parse_tables import _sqlglot_dialect

logger = logging.getLogger(__name__)

# Token types that unambiguously identify a PL/SQL unit kind right after
# `CREATE OR REPLACE`. `PACKAGE` (and `BODY`) are not sqlglot keywords in the
# oracle/generic tokenizers -- they tokenize as plain `VAR`, so they're matched
# by text below instead.
_KIND_TOKENS: dict[TokenType, str] = {
    TokenType.PROCEDURE: "procedure",
    TokenType.FUNCTION: "function",
    TokenType.TRIGGER: "trigger",
    TokenType.VIEW: "view",
}

# Tokens that end a unit's "signature" (header) -- the first of `AS`/`IS`/`BEGIN`
# encountered after the unit's name closes the signature.
_SIGNATURE_TERMINATORS = {TokenType.ALIAS, TokenType.IS, TokenType.BEGIN}


def _match_kind(tokens: list[Token], i: int) -> tuple[str, int] | None:
    """If `tokens[i]` starts a recognized PL/SQL kind, return `(kind, name_idx)`.

    `name_idx` is the index of the token holding the unit's identifier.
    Returns `None` if `tokens[i]` isn't a PL/SQL unit keyword.
    """
    if i >= len(tokens):
        return None
    tok = tokens[i]

    if tok.token_type in _KIND_TOKENS:
        return _KIND_TOKENS[tok.token_type], i + 1

    if tok.token_type == TokenType.VAR and tok.text.upper() == "PACKAGE":
        j = i + 1
        is_body = (
            j < len(tokens)
            and tokens[j].token_type == TokenType.VAR
            and tokens[j].text.upper() == "BODY"
        )
        if is_body:
            return "package", j + 1
        return "package", j

    return None


def _dotted_name_end(tokens: list[Token], name_idx: int) -> int:
    """Index (exclusive) past a possibly schema-qualified name starting at
    `name_idx` -- consumes `ident (DOT ident)*` so `schema.proc_name` is kept
    whole rather than truncated to just `schema`.
    """
    j = name_idx + 1
    n = len(tokens)
    while j + 1 < n and tokens[j].token_type == TokenType.DOT:
        j += 2  # skip the DOT and the identifier after it
    return j


def _find_unit_starts(tokens: list[Token]) -> list[tuple[int, str, int]]:
    """Find every top-level unit start: `(create_token_idx, kind, name_token_idx)`."""
    starts: list[tuple[int, str, int]] = []
    n = len(tokens)
    i = 0
    while i < n:
        tok = tokens[i]
        if tok.token_type == TokenType.CREATE:
            j = i + 1
            if (
                j + 1 < n
                and tokens[j].token_type == TokenType.OR
                and tokens[j + 1].token_type == TokenType.REPLACE
            ):
                j += 2
                match = _match_kind(tokens, j)
                if match is not None:
                    kind, name_idx = match
                    if name_idx < n:
                        starts.append((i, kind, name_idx))
        i += 1
    return starts


def _is_standalone_slash(sql: str, slash_start: int) -> bool:
    """True when the `/` at char offset `slash_start` is the SQL*Plus terminator:
    alone on its own line -- only whitespace before it back to the line start
    (or start of source), and only whitespace after it to the newline (or EOF).

    A `/` used as the arithmetic division operator always has a non-whitespace
    neighbour on its line (an operand), so this distinguishes the two without
    any regex -- purely char inspection around the tokenizer-provided offset.
    """
    line_start = sql.rfind("\n", 0, slash_start) + 1
    if sql[line_start:slash_start].strip() != "":
        return False
    line_end = sql.find("\n", slash_start + 1)
    tail = sql[slash_start + 1 :] if line_end == -1 else sql[slash_start + 1 : line_end]
    return tail.strip() == ""


def _unit_end_char(tokens: list[Token], start_idx: int, boundary_char: int, sql: str) -> int:
    """Char offset where this unit's body ends: the next *standalone* top-level
    `/` terminator (a `/` alone on its own line -- the SQL*Plus terminator, NOT
    an arithmetic division `/`) strictly before `boundary_char` (the next unit's
    start, or end of source), else `boundary_char` itself.
    """
    for tok in tokens[start_idx:]:
        if tok.start >= boundary_char:
            break
        if tok.token_type == TokenType.SLASH and _is_standalone_slash(sql, tok.start):
            return tok.start
    return boundary_char


def _signature_end_char(tokens: list[Token], name_idx: int, unit_end_char: int) -> int:
    """Char offset where the unit's signature (header) ends: the first
    `AS`/`IS`/`BEGIN` token after the name, else the unit's own end.
    """
    for tok in tokens[name_idx:]:
        if tok.start >= unit_end_char:
            break
        if tok.token_type in _SIGNATURE_TERMINATORS:
            return tok.start
    return unit_end_char


def parse_plsql(sql: str, dialect: str) -> list[PlsqlObject]:
    """Split `sql` into top-level PL/SQL units (`PACKAGE[ BODY]`, `PROCEDURE`,
    `FUNCTION`, `TRIGGER`, `VIEW`) declared via `CREATE OR REPLACE`.

    `dialect` is the logical `"oracle"`/`"db2"` label (mapped to a sqlglot
    dialect via the shared `_sqlglot_dialect` helper for tokenizing only --
    PL/SQL bodies are never handed to sqlglot's parser). Each returned
    `PlsqlObject` carries its full body verbatim (an exact slice of `sql`) in
    `body_oracle` or `body_db2` per `dialect`, plus `name`, `kind`, and
    `signature` (the header text up to `AS`/`IS`/`BEGIN`).
    """
    sqlglot_dialect = _sqlglot_dialect(dialect)
    tokenizer = Dialect.get_or_raise(sqlglot_dialect).tokenizer_class()
    tokens = tokenizer.tokenize(sql)

    starts = _find_unit_starts(tokens)

    objects: list[PlsqlObject] = []
    for i, (start_idx, kind, name_idx) in enumerate(starts):
        start_char = tokens[start_idx].start
        boundary_char = tokens[starts[i + 1][0]].start if i + 1 < len(starts) else len(sql)
        end_char = _unit_end_char(tokens, start_idx, boundary_char, sql)
        sig_end_char = _signature_end_char(tokens, name_idx, end_char)

        name_end_idx = _dotted_name_end(tokens, name_idx)
        name = sql[tokens[name_idx].start : tokens[name_end_idx - 1].end + 1]

        obj = PlsqlObject(
            name=name,
            module="",
            kind=kind,
            signature=sql[start_char:sig_end_char].strip(),
            dialects={dialect},
        )
        body = sql[start_char:end_char]
        if dialect == "db2":
            obj.body_db2 = body
        else:
            obj.body_oracle = body
        objects.append(obj)

    return objects

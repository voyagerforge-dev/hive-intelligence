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


def _unit_end_char(tokens: list[Token], start_idx: int, boundary_char: int) -> int:
    """Char offset where this unit's body ends: the next top-level `/`
    terminator strictly before `boundary_char` (the next unit's start, or end
    of source), else `boundary_char` itself.
    """
    for tok in tokens[start_idx:]:
        if tok.start >= boundary_char:
            break
        if tok.token_type == TokenType.SLASH:
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
        end_char = _unit_end_char(tokens, start_idx, boundary_char)
        sig_end_char = _signature_end_char(tokens, name_idx, end_char)

        obj = PlsqlObject(
            name=tokens[name_idx].text,
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

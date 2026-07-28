"""Split `CREATE OR REPLACE` PL/SQL units from Oracle and DB2 source into `PlsqlObject`s.

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

from hivedbparse.model import PlsqlObject
from hivedbparse.parse_tables import _sqlglot_dialect

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

# Optional Oracle view modifiers that can appear between `CREATE OR REPLACE`
# and the `VIEW` keyword (`FORCE`, `NO FORCE`, `EDITIONABLE`,
# `NONEDITIONABLE`, in any combination/order Oracle allows) -- none of them
# are sqlglot keywords in the oracle/generic tokenizers, so they tokenize as
# plain `VAR` and must be skipped (case-insensitive) before the kind check,
# or the real kind keyword right after them is never found.
_OPTIONAL_VIEW_MODIFIERS = {"FORCE", "NO", "EDITIONABLE", "NONEDITIONABLE"}

# PL/SQL "kinds" that are recognized (so a real object isn't misreported as
# an unrecognized unit) but are deliberately NOT carded: known non-object
# constructs.
#   `variable`  = DB2's `CREATE OR REPLACE VARIABLE <name> <type>` global
#                 variable declaration.
#   `type`/`type body` = user-defined collection/array/object TYPEs (Oracle
#                 `AS TABLE OF ...`/`AS OBJECT (...)`, DB2 `AS <t> ARRAY[]`)
#                 -- helper types, not documented schema objects. All corpus
#                 occurrences are such helpers.
#   `sequence`  = DB2's `CREATE OR REPLACE SEQUENCE <name> ...`. Sequences are
#                 a table-side concern already handled by `parse_aux` (which
#                 attaches them to their owning table); DB2 just spells them
#                 with `OR REPLACE`, so `_match_kind` must recognize them here
#                 to keep them off the unrecognized-unit gate. Not carded on
#                 the PL/SQL side.
#   `synonym`   = `CREATE OR REPLACE SYNONYM x FOR y[@dblink]` -- an alias, not
#                 a documented schema object.
#   `alias`/`nickname` = DB2's `CREATE OR REPLACE ALIAS x FOR TABLE y` and
#                 `CREATE OR REPLACE NICKNAME x FOR y` -- the DB2 spellings of a
#                 synonym/remote-table reference; an alias to another object,
#                 not a documented schema object of its own.
# None of these are schema objects the OKF cards document.
SKIP_KINDS = {"variable", "type", "type body", "sequence", "synonym", "alias", "nickname"}


def _skip_optional_view_modifiers(tokens: list[Token], i: int) -> int:
    """Advance `i` past any run of optional view modifier tokens (see
    `_OPTIONAL_VIEW_MODIFIERS`) so `_match_kind` sees the real kind keyword.
    """
    n = len(tokens)
    while (
        i < n
        and tokens[i].token_type == TokenType.VAR
        and tokens[i].text.upper() in _OPTIONAL_VIEW_MODIFIERS
    ):
        i += 1
    return i


def _match_kind(tokens: list[Token], i: int) -> tuple[str, int] | None:
    """If `tokens[i]` starts a recognized PL/SQL kind, return `(kind, name_idx)`.

    `name_idx` is the index of the token holding the unit's identifier.
    Returns `None` if `tokens[i]` isn't a PL/SQL unit keyword.
    """
    if i >= len(tokens):
        return None

    i = _skip_optional_view_modifiers(tokens, i)
    if i >= len(tokens):
        return None
    tok = tokens[i]

    if tok.token_type in _KIND_TOKENS:
        return _KIND_TOKENS[tok.token_type], i + 1

    # `SEQUENCE` has its own token type; recognized only so it's cleanly
    # skipped (SKIP_KINDS), never carded here -- see `parse_aux` for the real
    # table-side handling.
    if tok.token_type == TokenType.SEQUENCE:
        return "sequence", i + 1

    # `SYNONYM`/`ALIAS`/`NICKNAME` are not sqlglot keywords -- each tokenizes as
    # a plain `VAR`. All three are name-aliases for another object (Oracle
    # `SYNONYM`, DB2 `ALIAS`/`NICKNAME`), recognized only so they're cleanly
    # skipped (SKIP_KINDS) rather than flagged as unrecognized units.
    if tok.token_type == TokenType.VAR and tok.text.upper() in {"SYNONYM", "ALIAS", "NICKNAME"}:
        return tok.text.lower(), i + 1

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

    if tok.token_type == TokenType.VAR and tok.text.upper() == "VARIABLE":
        return "variable", i + 1

    if tok.token_type == TokenType.VAR and tok.text.upper() == "TYPE":
        j = i + 1
        is_body = (
            j < len(tokens)
            and tokens[j].token_type == TokenType.VAR
            and tokens[j].text.upper() == "BODY"
        )
        if is_body:
            return "type body", j + 1
        return "type", j

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
    """Find every top-level unit start: `(create_token_idx, kind, name_token_idx)`.

    Matches both `CREATE OR REPLACE <kind> ...` and bare `CREATE <kind> ...`
    (the `OR REPLACE` is optional) -- inline triggers/views in the Product
    module files are frequently plain `CREATE TRIGGER`/`CREATE VIEW`/
    `CREATE FORCE VIEW`. The kind is decided entirely by `_match_kind`, which
    only recognizes the PL/SQL unit keywords (package/procedure/function/
    trigger/view/type[ body]/variable) -- so `CREATE TABLE`/`CREATE INDEX`/
    `CREATE SEQUENCE`/`CREATE GLOBAL TEMPORARY TABLE` never match here and stay
    with the table path.
    """
    starts: list[tuple[int, str, int]] = []
    n = len(tokens)
    i = 0
    while i < n:
        if tokens[i].token_type == TokenType.CREATE:
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


def _find_unrecognized_units(tokens: list[Token]) -> list[int]:
    """`create_token_idx` for every top-level `CREATE OR REPLACE` whose
    following object-kind keyword is NOT a recognized PL/SQL unit kind
    (`package`/`procedure`/`function`/`trigger`/`view`).

    A `CREATE OR REPLACE` unambiguously introduces a replaceable schema
    object, so one whose kind keyword `_match_kind` can't classify (a typo'd
    `PROCEEDURE`, an unsupported object kind, ...) is an *intended unit that
    parsed to nothing* -- it must be surfaced, never silently dropped. The
    runner logs these via `parse_plsql`'s warning so its `_capture_warnings`
    feeds them into `unparsed` and the verification gate fails.
    """
    unrecognized: list[int] = []
    n = len(tokens)
    i = 0
    while i < n:
        if tokens[i].token_type == TokenType.CREATE:
            j = i + 1
            if (
                j + 1 < n
                and tokens[j].token_type == TokenType.OR
                and tokens[j + 1].token_type == TokenType.REPLACE
            ):
                j += 2
                if j < n and _match_kind(tokens, j) is None:
                    unrecognized.append(i)
        i += 1
    return unrecognized


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
    `FUNCTION`, `TRIGGER`, `VIEW`) declared via `CREATE [OR REPLACE] ...` (the
    `OR REPLACE` is optional -- inline module-file triggers/views are often a
    bare `CREATE TRIGGER`/`CREATE VIEW`).

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

    for create_idx in _find_unrecognized_units(tokens):
        logger.warning(
            "hivedbparse: unrecognized PL/SQL unit (CREATE OR REPLACE with no known kind): %.80s",
            sql[tokens[create_idx].start :].strip(),
        )

    objects: list[PlsqlObject] = []
    for i, (start_idx, kind, name_idx) in enumerate(starts):
        if kind in SKIP_KINDS:
            # Known non-object construct (class 3): recognized so it's never
            # misreported as an unrecognized unit, but not carded -- e.g. a
            # DB2 `CREATE OR REPLACE VARIABLE` global variable.
            logger.info(
                "hivedbparse: skipping known non-object PL/SQL construct (%s): %.80s",
                kind,
                sql[tokens[start_idx].start :].strip(),
            )
            continue

        start_char = tokens[start_idx].start
        boundary_char = tokens[starts[i + 1][0]].start if i + 1 < len(starts) else len(sql)
        end_char = _unit_end_char(tokens, start_idx, boundary_char, sql)
        sig_end_char = _signature_end_char(tokens, name_idx, end_char)

        name_end_idx = _dotted_name_end(tokens, name_idx)
        # Build the name from token *text* (not a raw source slice) so a quoted
        # identifier like "IMPORT_COMB_LANE_DTL" yields a clean, unquoted name
        # -- the tokenizer already strips the surrounding double-quotes from an
        # IDENTIFIER's text, and a DOT token's text is ".", so a dotted
        # SCHEMA."FOO" reassembles as SCHEMA.FOO (quotes stripped per
        # component). This mirrors how parse_tables yields unquoted names.
        name = "".join(tok.text for tok in tokens[name_idx:name_end_idx])

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

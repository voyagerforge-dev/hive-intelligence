"""Render `Table`/`PlsqlObject` models into OKF `dbobject` markdown cards.

One card per object (design spec Sec. 4): a `table_card` (columns + PK/FK/
index/sequence/trigger sections) and a `plsql_card` (signature + full body).
Everything sourced from `COMMENT ON ...`/DDL text (comments, types, bodies) is
rendered **verbatim** -- this module never fabricates or normalizes it. The
two correctness hazards called out in the design are handled explicitly:

- A comment containing `|` would otherwise break a markdown table row, so
  `|` is escaped to `\\|` when a comment is placed in the Columns table.
- Frontmatter is emitted with `yaml.safe_dump` (the same library okf-serve's
  loader uses to parse it back with `yaml.safe_load`), so a comment containing
  a `:` or other YAML-special character is always quoted/escaped correctly
  instead of hand-rolled and risking invalid YAML.
"""

from __future__ import annotations

import yaml

from okfdbparse.model import Column, PlsqlObject, Table

# Canonical dialect order for `platform:` frontmatter and derived source paths.
_DIALECT_ORDER = ("oracle", "db2")
_DIALECT_DIR = {"oracle": "Oracle", "db2": "DB2"}

_MISSING_TYPE = "—"  # em dash: column absent from that dialect


def card_id(obj: Table | PlsqlObject) -> str:
    """`wms/db/tables/<NAME>` for a `Table`, `wms/db/plsql/<NAME>` for a `PlsqlObject`."""
    if isinstance(obj, Table):
        return f"wms/db/tables/{obj.name}"
    if isinstance(obj, PlsqlObject):
        return f"wms/db/plsql/{obj.name}"
    raise TypeError(f"okfdbparse: card_id: unsupported object type {type(obj)!r}")


def _platform(dialects: set[str]) -> list[str]:
    return [d for d in _DIALECT_ORDER if d in dialects]


def _frontmatter(fields: dict) -> str:
    dumped = yaml.safe_dump(fields, sort_keys=False, default_flow_style=False, allow_unicode=True)
    return f"---\n{dumped}---\n"


def _esc_cell(text: str) -> str:
    """Escape `|` so a comment can't be mistaken for a markdown table column break."""
    return text.replace("|", "\\|")


# ---------------------------------------------------------------------------
# Table cards
# ---------------------------------------------------------------------------


def _table_title(t: Table) -> str:
    return f"{t.name} — {t.comment}" if t.comment else t.name


def _table_tags(t: Table) -> list[str]:
    return ["table", t.module]


def _table_sources(t: Table) -> list[str]:
    """The real file(s) `t` was read from, when the runner set them; else a
    synthesized `<module>.sql` path (correct for tables, since a module's
    `.sql` file *is* named after the module -- see `_plsql_sources` for why
    PL/SQL cards can't use the same synthesis)."""
    if t.source_files:
        return list(t.source_files)
    return [
        f"{_DIALECT_DIR[d]}/DBScripts/Product/{t.module}.sql"
        for d in _DIALECT_ORDER
        if d in t.dialects
    ]


def _table_related(t: Table) -> list[str]:
    related: list[str] = []
    for _col, ref_table, _ref_col in t.fks:
        rid = f"wms/db/tables/{ref_table}"
        if rid not in related:
            related.append(rid)
    return related


def _table_frontmatter(t: Table) -> dict:
    return {
        "type": "dbobject",
        "kind": "table",
        "title": _table_title(t),
        "description": t.comment,
        "product": "wms",
        "module": t.module,
        "platform": _platform(t.dialects),
        "tags": _table_tags(t),
        "related": _table_related(t),
        "sources": _table_sources(t),
    }


def _type_cell(type_text: str | None) -> str:
    return type_text if type_text else _MISSING_TYPE


def _column_row(c: Column, pk: list[str]) -> str:
    null = "NOT NULL" if c.not_null else ""
    key = "PK" if c.name in pk else ""
    return (
        f"| {c.name} | {_type_cell(c.type_oracle)} | {_type_cell(c.type_db2)} | "
        f"{null} | {key} | {_esc_cell(c.comment)} |"
    )


def _columns_table(t: Table) -> str:
    lines = [
        "| Column | Oracle type | DB2 type | Null | Key | Description |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend(_column_row(c, t.pk) for c in t.columns)
    return "\n".join(lines)


def _pk_section(t: Table) -> str:
    return ", ".join(t.pk) if t.pk else "none"


def _fks_section(t: Table) -> str:
    if not t.fks:
        return "none"
    return "\n".join(
        f"{col} → {ref_table}({ref_col})   → wms/db/tables/{ref_table}"
        for col, ref_table, ref_col in t.fks
    )


def _indexes_section(t: Table) -> str:
    if not t.indexes:
        return "none"
    lines = []
    for name, cols, unique in t.indexes:
        suffix = " [UNIQUE]" if unique else ""
        lines.append(f"{name} ({', '.join(cols)}){suffix}")
    return "\n".join(lines)


def _sequences_section(t: Table) -> str:
    return "\n".join(t.sequences) if t.sequences else "none"


def _triggers_section(t: Table) -> str:
    if not t.triggers:
        return "none"
    return "\n".join(f"{name} → wms/db/plsql/{name}" for name in t.triggers)


def table_card(t: Table) -> str:
    """Render `t` as an OKF `dbobject`/`table` markdown card (design Sec. 4.1)."""
    body_lines = [f"# {t.name}  (table · module {t.module})", ""]
    if t.comment:
        body_lines.append(t.comment)
        body_lines.append("")
    body_lines += [
        "## Columns",
        _columns_table(t),
        "",
        "## Primary key",
        _pk_section(t),
        "",
        "## Foreign keys",
        _fks_section(t),
        "",
        "## Indexes",
        _indexes_section(t),
        "",
        "## Sequences",
        _sequences_section(t),
        "",
        "## Triggers",
        _triggers_section(t),
        "",
    ]
    return _frontmatter(_table_frontmatter(t)) + "\n" + "\n".join(body_lines)


# ---------------------------------------------------------------------------
# PL/SQL cards
# ---------------------------------------------------------------------------


def _plsql_header_text(o: PlsqlObject) -> str:
    """Header comment if present, else a one-line summary taken verbatim from
    the object's own captured signature (never a fabricated description).
    """
    if o.comment:
        return o.comment
    first_line = o.signature.strip().splitlines()[0].strip() if o.signature.strip() else ""
    return first_line


def _plsql_title(o: PlsqlObject) -> str:
    header = _plsql_header_text(o)
    return f"{o.name} — {header}" if header else o.name


def _plsql_tags(o: PlsqlObject) -> list[str]:
    return ["plsql", o.kind, o.module]


def _plsql_sources(o: PlsqlObject) -> list[str]:
    """The real file(s) `o` was read from, when the runner set them. A
    PL/SQL unit's real file lives at `PLSQL_Objects/<file>.sql`, named per
    *file* (not necessarily per object) -- unlike a table's module file, this
    can't be reliably synthesized from `o.name`/`o.module` alone, so the
    fallback below is a best-effort guess only used when `source_files` is
    unset (e.g. in unit tests that build a `PlsqlObject` directly)."""
    if o.source_files:
        return list(o.source_files)
    return [
        f"{_DIALECT_DIR[d]}/DBScripts/Product/PLSQL_Objects/{o.name}.sql"
        for d in _DIALECT_ORDER
        if d in o.dialects
    ]


def _plsql_frontmatter(o: PlsqlObject) -> dict:
    return {
        "type": "dbobject",
        "kind": o.kind,
        "title": _plsql_title(o),
        "description": _plsql_header_text(o),
        "product": "wms",
        "module": o.module,
        "platform": _platform(o.dialects),
        "tags": _plsql_tags(o),
        "sources": _plsql_sources(o),
    }


def plsql_card(o: PlsqlObject) -> str:
    """Render `o` as an OKF `dbobject`/`<kind>` markdown card (design Sec. 4.2)."""
    body_lines = [
        f"# {o.name}  ({o.kind} · module {o.module})",
        "",
        "## Signature / spec",
        "```sql",
        o.signature,
        "```",
        "",
        "## Source (Oracle)",
        "```sql",
        o.body_oracle,
        "```",
        "",
        "## Source (DB2)",
    ]
    if o.body_db2:
        body_lines += ["```sql", o.body_db2, "```"]
    else:
        body_lines.append("Identical to Oracle.")
    body_lines.append("")
    return _frontmatter(_plsql_frontmatter(o)) + "\n" + "\n".join(body_lines)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def manifest_line(obj: Table | PlsqlObject) -> dict:
    """`{id, kind, module, product, title, description, tags}` for the manifest index."""
    if isinstance(obj, Table):
        return {
            "id": card_id(obj),
            "kind": "table",
            "module": obj.module,
            "product": "wms",
            "title": _table_title(obj),
            "description": obj.comment,
            "tags": _table_tags(obj),
        }
    if isinstance(obj, PlsqlObject):
        return {
            "id": card_id(obj),
            "kind": obj.kind,
            "module": obj.module,
            "product": "wms",
            "title": _plsql_title(obj),
            "description": _plsql_header_text(obj),
            "tags": _plsql_tags(obj),
        }
    raise TypeError(f"okfdbparse: manifest_line: unsupported object type {type(obj)!r}")

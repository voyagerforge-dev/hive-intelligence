"""Reconcile Oracle and DB2 parse output into one dialect-tagged model per object.

`parse_tables`/`parse_plsql` (Tasks 1-3) run once per dialect and know nothing
about each other. This module is the only place that compares the two runs:
tables are unioned by name (Oracle is authoritative for structure -- PK/FK/
index/comment -- DB2 only contributes `type_db2` on matching columns), and
PL/SQL units are unioned by name with a whitespace-normalized body diff so a
card can render "Identical to Oracle" instead of two copies of the same body.

PL/SQL packages need one extra step first: `parse_plsql` emits a package's
spec (`CREATE OR REPLACE PACKAGE ...`) and body (`CREATE OR REPLACE PACKAGE
BODY ...`) as two separate same-name `PlsqlObject`s (Task 3 never merges
them -- it only slices unit boundaries). `reconcile_plsql` collapses that pair
into a single object *per dialect* before doing the cross-dialect union, so
exactly one card is emitted per package.
"""

from __future__ import annotations

import re
from dataclasses import replace

from hivedbparse.model import PlsqlObject, Table


def _normalize_ws(text: str) -> str:
    """Collapse all whitespace runs to a single space, for body-equality checks
    that shouldn't care about reformatting between the two dialect sources.
    """
    return re.sub(r"\s+", " ", text).strip()


def reconcile_tables(oracle: dict[str, Table], db2: dict[str, Table]) -> list[Table]:
    """Union `oracle`/`db2` tables by name.

    For a name present in both, the Oracle `Table` is authoritative for
    structure (comment/pk/fks/indexes/sequences/triggers) -- DB2 only fills
    `type_db2` onto matching columns by name (a column present in just one
    dialect keeps the other dialect's type `None`). `dialects` is the union.
    Neither input mapping/Table/Column is mutated.
    """
    merged: dict[str, Table] = {}
    order: list[str] = []

    for name, table in oracle.items():
        merged[name] = replace(
            table, columns=[replace(c) for c in table.columns], dialects=set(table.dialects)
        )
        order.append(name)

    for name, table in db2.items():
        if name not in merged:
            merged[name] = replace(
                table, columns=[replace(c) for c in table.columns], dialects=set(table.dialects)
            )
            order.append(name)
            continue

        existing = merged[name]
        existing.dialects |= table.dialects
        by_col = {c.name: c for c in existing.columns}
        for col in table.columns:
            if col.name in by_col:
                by_col[col.name].type_db2 = col.type_db2
            else:
                existing.columns.append(replace(col))

    return [merged[n] for n in order]


def _looks_like_package_body(text: str) -> bool:
    """True when `text` (a captured unit body) is a `PACKAGE BODY`, not a spec."""
    return re.match(r"\s*CREATE\s+OR\s+REPLACE\s+PACKAGE\s+BODY\b", text, re.IGNORECASE) is not None


def _merge_package_units(objs: list[PlsqlObject], dialect: str) -> list[PlsqlObject]:
    """Collapse same-name `kind="package"` spec+body pairs from one dialect's
    `parse_plsql` output into a single `PlsqlObject`: the spec's captured text
    becomes `signature`, the body's captured text becomes `body_<dialect>`. If
    only one of the pair is present, it's placed in whichever field matches
    what it is (spec -> signature, body -> body_<dialect>) and the other field
    stays at its default. Non-package units pass through unchanged (one unit
    per name already).
    """
    attr = f"body_{dialect}"
    merged: dict[str, PlsqlObject] = {}
    order: list[str] = []

    for obj in objs:
        if obj.kind != "package":
            # Same-name units in one dialect collapse LAST-wins. The runner
            # feeds units lowest-precedence-first (Seed re-declarations, then
            # Product-inline, then the dedicated PLSQL_Objects/ file), so the
            # highest-precedence definition is the one that survives -- see
            # `run._ordered_plsql`.
            if obj.name not in merged:
                order.append(obj.name)
            merged[obj.name] = replace(obj, dialects=set(obj.dialects))
            continue

        if obj.name not in merged:
            order.append(obj.name)
            merged[obj.name] = PlsqlObject(
                name=obj.name, module=obj.module, kind="package", dialects=set()
            )
        target = merged[obj.name]
        target.dialects |= obj.dialects

        text = getattr(obj, attr)
        if _looks_like_package_body(text):
            setattr(target, attr, text)
        else:
            target.signature = text

    return [merged[n] for n in order]


def reconcile_plsql(oracle: list[PlsqlObject], db2: list[PlsqlObject]) -> list[PlsqlObject]:
    """Union `oracle`/`db2` PL/SQL units by name (after collapsing each
    dialect's package spec+body pairs into one object -- see module docstring).

    For a name present in both, `dialects` is the union; if `body_db2` equals
    `body_oracle` under whitespace normalization, `body_db2` is cleared to
    `""` (the card renders "Identical to Oracle") -- otherwise both bodies are
    kept as captured.
    """
    oracle_merged = _merge_package_units(oracle, "oracle")
    db2_merged = _merge_package_units(db2, "db2")

    merged: dict[str, PlsqlObject] = {}
    order: list[str] = []

    for obj in oracle_merged:
        merged[obj.name] = obj
        order.append(obj.name)

    for obj in db2_merged:
        if obj.name not in merged:
            merged[obj.name] = obj
            order.append(obj.name)
            continue

        existing = merged[obj.name]
        existing.dialects |= obj.dialects
        if _normalize_ws(obj.body_db2) == _normalize_ws(existing.body_oracle):
            existing.body_db2 = ""
        else:
            existing.body_db2 = obj.body_db2

    return [merged[n] for n in order]

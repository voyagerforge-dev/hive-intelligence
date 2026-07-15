"""End-to-end runner: WMOS Oracle/DB2 DDL tree -> OKF `dbobject` cards + manifest.

Walks exactly two locations per dialect -- `DBScripts/Product/*.sql` (tables)
and `DBScripts/Product/PLSQL_Objects/*.sql` (PL/SQL units) -- so `Seed/`,
`Archive/`, `Upgrade/` and `CreateSchema/` (siblings of `PLSQL_Objects/` under
`Product/`) are skipped simply by never being walked: a non-recursive
`Path.glob("*.sql")` on `Product/` only ever sees files directly in it, never
files one directory down.

Each object's `module` is set from its source filename stem (`DOM.sql` ->
`DOM`). Each object's `source_files` is set to the actual repo-relative
path(s) it was read from (Oracle and/or DB2) -- this is what makes a PL/SQL
card's `sources:` point at its real `PLSQL_Objects/<file>.sql` rather than the
synthesized-but-wrong `<module>.sql` that `emit` falls back to when
`source_files` is unset (see `okfdbparse.emit._plsql_sources`).

The **verification gate** is hard -- no object may be silently dropped, every
drop surfaces as `RunError`. `run()` always finishes the full walk (so its
`RunError` can report exactly what did and didn't work), then raises if:

- any statement/unit failed to parse (`unparsed` non-empty). Never silently
  dropped: `parse_tables`/`parse_plsql` log a WARNING with a source snippet
  instead of skipping -- including a `CREATE OR REPLACE` whose object-kind
  keyword matches no known PL/SQL kind (a typo'd/unsupported unit).
  `_capture_warnings` below captures those per-file so the runner attributes
  each to the file it came from.
- two definitions of the same name appear in the *same* dialect tree
  (`collisions` non-empty) -- two `CREATE TABLE T` in one dialect, or two
  same-name PL/SQL units in one dialect that are NOT a package spec/body
  pair. This is detected before the losing object is overwritten. A
  cross-dialect Oracle/DB2 merge of the same name, and a package spec+body
  pair within one dialect, are legitimate merges and are NOT collisions.
- (kept, though the two gates above are the real protection) a kind's
  emitted-card count doesn't match its parsed-object count.
"""

from __future__ import annotations

import argparse
import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from okfdbparse.emit import manifest_line, plsql_card, table_card
from okfdbparse.model import PlsqlObject, Table
from okfdbparse.parse_aux import apply_aux
from okfdbparse.parse_plsql import parse_plsql
from okfdbparse.parse_tables import parse_tables
from okfdbparse.reconcile import _looks_like_package_body, reconcile_plsql, reconcile_tables

_DIALECTS = ("oracle", "db2")
_DIALECT_DIR = {"oracle": "Oracle", "db2": "DB2"}


class RunError(RuntimeError):
    """Raised when the verification gate fails: unparsed objects, same-dialect
    same-name duplicate definitions, or a kind's emitted-card count doesn't
    match its parsed-object count."""


@dataclass
class RunReport:
    """Per-kind parsed/emitted counts, every unparsed statement/unit (as
    `"<repo-relative file>: <warning message with snippet>"`), and every
    same-dialect same-name duplicate definition (a genuine collision -- NOT a
    legit Oracle/DB2 cross-dialect merge or a package spec/body pair)."""

    counts: dict[str, dict[str, int]] = field(
        default_factory=lambda: {
            "table": {"parsed": 0, "emitted": 0},
            "plsql": {"parsed": 0, "emitted": 0},
        }
    )
    unparsed: list[str] = field(default_factory=list)
    collisions: list[str] = field(default_factory=list)


@contextmanager
def _capture_warnings(logger_name: str):
    """Capture WARNING+ messages logged by `logger_name` for the duration of
    the `with` block. `parse_tables`/`parse_plsql` log one WARNING (with a
    source snippet) per statement/unit they couldn't parse instead of
    swallowing it; this lets the runner see those without changing either
    module's return type (which existing Task 1-3 tests depend on)."""
    messages: list[str] = []

    class _Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    handler = _Handler(level=logging.WARNING)
    target = logging.getLogger(logger_name)
    target.addHandler(handler)
    try:
        yield messages
    finally:
        target.removeHandler(handler)


def _sql_files(directory: Path, limit_modules: int | None) -> list[Path]:
    """Sorted, non-recursive `*.sql` files directly in `directory` (empty
    list if it doesn't exist), capped to `limit_modules` when given."""
    if not directory.is_dir():
        return []
    files = sorted(directory.glob("*.sql"))
    return files[:limit_modules] if limit_modules is not None else files


def _record_source(sources: dict[str, list[str]], name: str, path: str) -> None:
    paths = sources.setdefault(name, [])
    if path not in paths:
        paths.append(path)


def _union_sources(*source_maps: dict[str, list[str]], name: str) -> list[str]:
    """Every repo-relative path recorded for `name` across dialects, Oracle
    first (dict iteration/insertion order), deduped."""
    merged: list[str] = []
    for source_map in source_maps:
        for path in source_map.get(name, []):
            if path not in merged:
                merged.append(path)
    return merged


def _parse_dialect_tables(
    src_root: Path,
    dialect: str,
    limit_modules: int | None,
    unparsed: list[str],
    collisions: list[str],
) -> tuple[dict[str, Table], dict[str, list[str]]]:
    product_dir = src_root / _DIALECT_DIR[dialect] / "DBScripts" / "Product"
    tables: dict[str, Table] = {}
    sources: dict[str, list[str]] = {}
    texts: list[str] = []

    for sql_file in _sql_files(product_dir, limit_modules):
        module = sql_file.stem
        text = sql_file.read_text()
        rel = f"{_DIALECT_DIR[dialect]}/DBScripts/Product/{sql_file.name}"

        with _capture_warnings("okfdbparse.parse_tables") as warnings:
            parsed = parse_tables(text, dialect)
        unparsed.extend(f"{rel}: {w}" for w in warnings)

        for name, table in parsed.items():
            table.module = module
            if name in tables:
                # Two CREATE TABLE of the same name in the SAME dialect tree:
                # first-file-wins would silently discard this one. Surface it
                # (and do NOT record this file as a source, so the surviving
                # object's sources: lists only files that actually contributed).
                prior = ", ".join(sources.get(name, [])) or "an earlier file"
                collisions.append(
                    f"{_DIALECT_DIR[dialect]} table {name}: duplicate CREATE TABLE in "
                    f"{rel} (already defined in {prior})"
                )
                continue
            _record_source(sources, name, rel)
            tables[name] = table

        texts.append(text)

    if texts:
        apply_aux(tables, "\n".join(texts), dialect)

    return tables, sources


def _is_legit_package_pair(objs: list[PlsqlObject], dialect: str) -> bool:
    """True when a group of same-name units in one dialect is a legitimate
    package spec/body pair (`reconcile._merge_package_units` merges these into
    one object), NOT a genuine collision. That means: every unit is a
    `package`, and the group holds at most one spec and at most one body --
    using the exact same spec-vs-body discriminator reconcile uses, so this
    never diverges from what reconcile will legitimately merge.
    """
    if not all(o.kind == "package" for o in objs):
        return False
    attr = f"body_{dialect}"
    bodies = sum(1 for o in objs if _looks_like_package_body(getattr(o, attr)))
    specs = len(objs) - bodies
    return bodies <= 1 and specs <= 1


def _detect_plsql_collisions(
    objects: list[PlsqlObject], dialect: str, collisions: list[str]
) -> None:
    """Flag same-name PL/SQL units within one dialect that are NOT a package
    spec/body pair -- two procedures/functions/... of the same name (or a
    duplicated spec/body) that reconcile's name-keyed union would silently
    collapse, dropping one object's body."""
    groups: dict[str, list[PlsqlObject]] = {}
    for obj in objects:
        groups.setdefault(obj.name, []).append(obj)
    for name, objs in groups.items():
        if len(objs) > 1 and not _is_legit_package_pair(objs, dialect):
            collisions.append(
                f"{_DIALECT_DIR[dialect]} plsql {name}: {len(objs)} same-name units in one "
                f"dialect that are not a package spec/body pair"
            )


def _parse_dialect_plsql(
    src_root: Path,
    dialect: str,
    limit_modules: int | None,
    unparsed: list[str],
    collisions: list[str],
) -> tuple[list[PlsqlObject], dict[str, list[str]]]:
    plsql_dir = src_root / _DIALECT_DIR[dialect] / "DBScripts" / "Product" / "PLSQL_Objects"
    objects: list[PlsqlObject] = []
    sources: dict[str, list[str]] = {}

    for sql_file in _sql_files(plsql_dir, limit_modules):
        module = sql_file.stem
        text = sql_file.read_text()
        rel = f"{_DIALECT_DIR[dialect]}/DBScripts/Product/PLSQL_Objects/{sql_file.name}"

        with _capture_warnings("okfdbparse.parse_plsql") as warnings:
            parsed = parse_plsql(text, dialect)
        unparsed.extend(f"{rel}: {w}" for w in warnings)

        for obj in parsed:
            obj.module = module
            _record_source(sources, obj.name, rel)
            objects.append(obj)

    _detect_plsql_collisions(objects, dialect, collisions)
    return objects, sources


def run(src_root: Path, out_dir: Path, *, limit_modules: int | None = None) -> RunReport:
    """Parse+reconcile every WMOS table/PL/SQL object under `src_root`, emit
    one card per object under `out_dir/{tables,plsql}/` plus
    `out_dir/manifest.jsonl`, and return the `RunReport`.

    Raises `RunError` (after completing the full run) if the verification
    gate fails -- see module docstring.
    """
    unparsed: list[str] = []
    collisions: list[str] = []

    oracle_tables, oracle_table_sources = _parse_dialect_tables(
        src_root, "oracle", limit_modules, unparsed, collisions
    )
    db2_tables, db2_table_sources = _parse_dialect_tables(
        src_root, "db2", limit_modules, unparsed, collisions
    )
    merged_tables = reconcile_tables(oracle_tables, db2_tables)
    for table in merged_tables:
        table.source_files = _union_sources(
            oracle_table_sources, db2_table_sources, name=table.name
        )

    oracle_plsql, oracle_plsql_sources = _parse_dialect_plsql(
        src_root, "oracle", limit_modules, unparsed, collisions
    )
    db2_plsql, db2_plsql_sources = _parse_dialect_plsql(
        src_root, "db2", limit_modules, unparsed, collisions
    )
    merged_plsql = reconcile_plsql(oracle_plsql, db2_plsql)
    for obj in merged_plsql:
        obj.source_files = _union_sources(oracle_plsql_sources, db2_plsql_sources, name=obj.name)

    report = RunReport(unparsed=unparsed, collisions=collisions)
    report.counts["table"]["parsed"] = len(merged_tables)
    report.counts["plsql"]["parsed"] = len(merged_plsql)

    tables_dir = out_dir / "tables"
    plsql_dir = out_dir / "plsql"
    tables_dir.mkdir(parents=True, exist_ok=True)
    plsql_dir.mkdir(parents=True, exist_ok=True)

    manifest_lines: list[dict] = []

    for table in merged_tables:
        (tables_dir / f"{table.name}.md").write_text(table_card(table))
        manifest_lines.append(manifest_line(table))
        report.counts["table"]["emitted"] += 1

    for obj in merged_plsql:
        (plsql_dir / f"{obj.name}.md").write_text(plsql_card(obj))
        manifest_lines.append(manifest_line(obj))
        report.counts["plsql"]["emitted"] += 1

    with (out_dir / "manifest.jsonl").open("w") as fh:
        for line in manifest_lines:
            fh.write(json.dumps(line) + "\n")

    if report.unparsed:
        raise RunError(
            f"okfdbparse: {len(report.unparsed)} unparsed statement(s)/unit(s) "
            f"(never silently skipped): {report.unparsed}"
        )
    if report.collisions:
        raise RunError(
            f"okfdbparse: {len(report.collisions)} same-dialect same-name duplicate "
            f"definition(s) (would silently drop an object): {report.collisions}"
        )
    for kind, counts in report.counts.items():
        if counts["parsed"] != counts["emitted"]:
            raise RunError(
                f"okfdbparse: emitted count != parsed count for {kind!r}: {counts}"
            )

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="okfdbparse",
        description="Parse WMOS Oracle/DB2 DDL into OKF dbobject cards + manifest.",
    )
    parser.add_argument("--src", required=True, type=Path, help="DDL tree root")
    parser.add_argument("--out", required=True, type=Path, help="cards + manifest output dir")
    parser.add_argument(
        "--limit-modules",
        type=int,
        default=None,
        help="cap the number of source files processed per dialect/kind (for smoke runs)",
    )
    args = parser.parse_args(argv)

    report = run(args.src, args.out, limit_modules=args.limit_modules)
    print(
        json.dumps(
            {
                "counts": report.counts,
                "unparsed": report.unparsed,
                "collisions": report.collisions,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

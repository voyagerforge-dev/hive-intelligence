"""End-to-end runner: WMOS Oracle/DB2 DDL tree -> OKF `dbobject` cards + manifest.

Walks three locations per dialect: `DBScripts/Product/*.sql` (module files,
non-recursive), the `DBScripts/Seed/Product/<module>/` base-schema catalogs
(`WMLM`/`CA`/`SLOT` -- the `*_Tables_PKs.sql` bundles where the classic WM
tables like `PROD_TRKG_TRAN`/`ACCESSORIAL` are declared, disjoint from the
module files; see `_dialect_table_files`), and `DBScripts/Product/PLSQL_Objects/*.sql`
(PL/SQL units). Under `Seed/Product`, per-table INSERT seed-data files (no
object DDL) are skipped by content (`_has_ddl`). The subdirectories *under*
`Product/` (`Product/Seed/`, `Product/Archive/`, `Product/Upgrade/`,
`Product/CreateSchema/`) and the non-`Product` `Seed/` subtrees
(`Seed/Archive/`, `Seed/Merges/`, `Seed/Shared/`) are still never walked -- the
`Product/*.sql` glob is non-recursive and the Seed walk is scoped to
`Seed/Product/`.

Each object's `module` is set from its source filename stem (`DOM.sql` ->
`DOM`). Each object's `source_files` is set to the actual repo-relative
path(s) it was read from (Oracle and/or DB2) -- this is what makes a PL/SQL
card's `sources:` point at its real `PLSQL_Objects/<file>.sql` rather than the
synthesized-but-wrong `<module>.sql` that `emit` falls back to when
`source_files` is unset (see `okfdbparse.emit._plsql_sources`).

The **verification gate** is hard on exactly ONE thing -- *unparsed* objects,
the only case that silently drops unique content. `run()` always finishes the
full walk (so its `RunError` can report exactly what did and didn't work),
then raises if any statement/unit failed to parse (`unparsed` non-empty):
`parse_tables`/`parse_plsql` log a WARNING with a source snippet instead of
skipping -- including a `CREATE OR REPLACE` whose object-kind keyword matches
no known PL/SQL kind (a typo'd/unsupported unit). `_capture_warnings` below
captures those per-file so the runner attributes each to the file it came from.

**Same-dialect same-name duplicates do NOT fail the run.** A duplicate is at
worst "we card one of two near-identical definitions" -- not the drop-of-
unique-content the gate guards against. So each duplicate is deduped (the
first-seen object is kept), BOTH source files are recorded in the surviving
object's `source_files`, and a line describing it (object, files, and whether
`identical` or `differs in <columns|body>`) is appended to `conflicts.log` in
the output dir -- fully visible, never silent, but never fatal. `RunReport`
exposes the deduped-`duplicates` list for visibility. NOT logged as
duplicates (they are legitimate merges): a cross-dialect Oracle/DB2 merge of
the same name, and a package spec+body pair within one dialect.

The kept count-match check (emitted == parsed per kind) is a cheap
consistency assertion, not the primary protection.
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
from okfdbparse.parse_aux import _SEQUENCE_DECL, _attach_sequence, apply_aux
from okfdbparse.parse_plsql import parse_plsql
from okfdbparse.parse_tables import parse_tables
from okfdbparse.reconcile import (
    _looks_like_package_body,
    _normalize_ws,
    reconcile_plsql,
    reconcile_tables,
)

logger = logging.getLogger(__name__)

_DIALECTS = ("oracle", "db2")
_DIALECT_DIR = {"oracle": "Oracle", "db2": "DB2"}


class RunError(RuntimeError):
    """Raised when the verification gate fails: unparsed objects (the only
    silent-drop-of-unique-content case), or a kind's emitted-card count
    doesn't match its parsed-object count."""


@dataclass
class RunReport:
    """Per-kind parsed/emitted counts, every unparsed statement/unit (as
    `"<repo-relative file>: <warning message with snippet>"`), and every
    same-dialect same-name duplicate that was deduped (`duplicates` -- visible
    but non-fatal; also written to `conflicts.log`). A legit Oracle/DB2
    cross-dialect merge or a package spec/body pair is NOT a duplicate."""

    counts: dict[str, dict[str, int]] = field(
        default_factory=lambda: {
            "table": {"parsed": 0, "emitted": 0},
            "plsql": {"parsed": 0, "emitted": 0},
        }
    )
    unparsed: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    # Aux statements that parsed fine but had nowhere to attach: a
    # comment/FK/index on a table outside the carded corpus, or a sequence whose
    # owning table couldn't be resolved. A SCOPE consequence, not a parser gap --
    # reported (`unattached.log`) and non-fatal, unlike `unparsed`.
    unattached: list[str] = field(default_factory=list)


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


def _table_structure_key(t: Table) -> tuple:
    """A hashable, order-insensitive fingerprint of a table's *structure* --
    its column set (name + both dialect types + not_null) and its primary-key
    set. Two same-name tables with an equal key produce an identical card, so
    a duplicate definition of one is benign (a shared table re-declared).
    Tablespace/storage isn't captured by the parser, so it never affects this.
    """
    columns = frozenset(
        (c.name, c.type_oracle, c.type_db2, c.not_null) for c in t.columns
    )
    return columns, frozenset(t.pk)


def _tables_same_structure(a: Table, b: Table) -> bool:
    return _table_structure_key(a) == _table_structure_key(b)


def _has_ddl(text: str) -> bool:
    """True if `text` declares an object we card (a `CREATE TABLE` or a
    `CREATE [OR REPLACE]` PL/SQL unit). Used to skip the thousands of per-table
    INSERT seed-data files under `Seed/Product/` -- they carry no object DDL,
    so parsing them would be pure waste (and bloat the `apply_aux` scan)."""
    upper = text.upper()
    return "CREATE TABLE" in upper or "CREATE OR REPLACE" in upper


def _dialect_table_files(
    src_root: Path, dialect: str, limit_modules: int | None
) -> list[tuple[Path, str, str, bool]]:
    """Every DDL source file feeding table parsing for a dialect, as
    `(path, module, rel, is_seed)`.

    The `Product/*.sql` module files come FIRST (`module` = filename stem),
    then the `Seed/Product/<module>/` base-schema catalogs (`module` = the
    module folder: `WMLM`/`CA`/`SLOT`). The classic WM/base tables (e.g.
    `PROD_TRKG_TRAN`, `ACCESSORIAL`, `ALLOC_PARM`) are declared only in those
    `Seed/Product/<module>/*_Tables_PKs.sql` catalogs, disjoint from the
    module files -- so they must be walked too. Product-first ordering makes
    the Product module definition win the keep-first dedup on the tables
    defined in both trees. (`Seed/Product` also holds per-table INSERT
    seed-data files with no DDL; `_parse_dialect_tables` skips those via
    `_has_ddl` after reading.)
    """
    ddir = _DIALECT_DIR[dialect]
    items: list[tuple[Path, str, str, bool]] = []
    product_dir = src_root / ddir / "DBScripts" / "Product"
    for f in _sql_files(product_dir, limit_modules):
        items.append((f, f.stem, f"{ddir}/DBScripts/Product/{f.name}", False))

    seed_root = src_root / ddir / "DBScripts" / "Seed" / "Product"
    if seed_root.is_dir():
        seed_files = sorted(seed_root.rglob("*.sql"))
        if limit_modules is not None:
            seed_files = seed_files[:limit_modules]
        for f in seed_files:
            rel_parts = f.relative_to(seed_root)
            module = rel_parts.parts[0]
            items.append(
                (f, module, f"{ddir}/DBScripts/Seed/Product/{rel_parts.as_posix()}", True)
            )
    return items


def _parse_dialect_tables(
    src_root: Path,
    dialect: str,
    limit_modules: int | None,
    unparsed: list[str],
    duplicates: list[str],
    unattached: list[str],
    sequence_names: list[str],
    plsql_objects: list[PlsqlObject],
    plsql_sources: dict[str, list[str]],
    seed_plsql_objects: list[PlsqlObject],
) -> tuple[dict[str, Table], dict[str, list[str]]]:
    """Parse every table-DDL source file for a dialect -- the `Product/*.sql`
    module files AND the `Seed/Product/<module>/` base-schema catalogs (see
    `_dialect_table_files`). Each file yields BOTH tables (via `parse_tables` +
    `apply_aux`) AND any inline PL/SQL units it declares (triggers/views/
    procedures/... via `parse_plsql` on the same text). Inline units are
    appended to the shared `plsql_objects`/`plsql_sources` accumulators (the
    runner also fills these from `PLSQL_Objects/`), with `module` from the
    filename stem (Product) or module folder (Seed) and the file recorded as
    the unit's source -- so a module-file trigger is carded with an accurate
    `sources:`, and any object appearing both inline and in `PLSQL_Objects` is
    handled by the shared reconcile/dedup path.
    """
    tables: dict[str, Table] = {}
    sources: dict[str, list[str]] = {}
    texts: list[str] = []

    for sql_file, module, rel, is_seed in _dialect_table_files(src_root, dialect, limit_modules):
        text = sql_file.read_text()
        # Seed/Product holds thousands of per-table INSERT seed-data files with
        # no object DDL -- skip them (never parse, never concat into apply_aux).
        if is_seed and not _has_ddl(text):
            continue

        with _capture_warnings("okfdbparse.parse_tables") as warnings:
            parsed = parse_tables(text, dialect)
        unparsed.extend(f"{rel}: {w}" for w in warnings)

        for name, table in parsed.items():
            table.module = module
            existing = tables.get(name)
            if existing is not None:
                # Two CREATE TABLE of the same name in the SAME dialect tree.
                # Never fatal: keep the first object (both cards are at worst
                # near-identical), record BOTH files as sources, and note the
                # duplicate (identical structure, or differing columns/pk) for
                # conflicts.log -- visible, never silent, never a hard fail.
                prior = ", ".join(sources.get(name, [])) or "an earlier file"
                verdict = (
                    "identical"
                    if _tables_same_structure(existing, table)
                    else "differs in columns/pk"
                )
                duplicates.append(
                    f"{_DIALECT_DIR[dialect]} table {name}: duplicate in {rel} "
                    f"(vs {prior}) -- {verdict}; kept first, deduped"
                )
                _record_source(sources, name, rel)
                continue
            _record_source(sources, name, rel)
            tables[name] = table

        # Inline PL/SQL declared in the SAME module file (triggers/views/
        # procedures/packages/functions). parse_plsql warnings flow into the
        # unparsed gate, so an inline unit is never silently dropped.
        with _capture_warnings("okfdbparse.parse_plsql") as pl_warnings:
            units = parse_plsql(text, dialect)
        unparsed.extend(f"{rel}: {w}" for w in pl_warnings)
        for obj in units:
            obj.module = module
            _record_source(plsql_sources, obj.name, rel)
            # A unit inline in a Seed catalog is only a re-declaration of a
            # Product unit: keep it in the lower-precedence bucket so it can
            # never clobber the Product definition (see `_ordered_plsql`).
            (seed_plsql_objects if is_seed else plsql_objects).append(obj)

        texts.append(text)

    if texts:
        # apply_aux warns on two SIBLING loggers and they mean different things:
        #   okfdbparse.parse_aux      -- attachable DDL we couldn't parse. A real
        #                                silent drop (a lost index/sequence/FK/
        #                                comment) -> routed into the hard gate.
        #   okfdbparse.aux_unattached -- parsed fine, but its target isn't carded
        #                                (or a sequence has no resolvable owner).
        #                                A scope consequence -> reported, non-fatal.
        # Capturing them separately is why they must not be parent/child loggers.
        with _capture_warnings("okfdbparse.parse_aux") as aux_failures:
            with _capture_warnings("okfdbparse.aux_unattached") as aux_unattached:
                apply_aux(tables, "\n".join(texts), dialect)
        prefix = f"{_DIALECT_DIR[dialect]} aux"
        unparsed.extend(f"{prefix}: {w}" for w in aux_failures)
        unattached.extend(f"{prefix}: {w}" for w in aux_unattached)
        # Collect sequence names for post-reconcile attachment (their owners live
        # in the MERGED table set, not this dialect's -- see `attach_sequences`).
        sequence_names.extend(_SEQUENCE_DECL.findall("\n".join(texts)))

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


def _detect_plsql_duplicates(
    objects: list[PlsqlObject], dialect: str, duplicates: list[str]
) -> None:
    """Note same-name PL/SQL units within one dialect that reconcile's
    name-keyed union collapses to one (keeping the first) -- visible via
    `conflicts.log`, never fatal. NOT noted (legitimate merges): a package
    spec/body pair (`_is_legit_package_pair`). For everything else, the note
    records whether the bodies are `identical` (a shared unit re-declared) or
    `differs in body` (near-identical multi-definitions across modules).
    """
    attr = f"body_{dialect}"
    groups: dict[str, list[PlsqlObject]] = {}
    for obj in objects:
        groups.setdefault(obj.name, []).append(obj)
    for name, objs in groups.items():
        if len(objs) <= 1 or _is_legit_package_pair(objs, dialect):
            continue
        identical = len({_normalize_ws(getattr(o, attr)) for o in objs}) == 1
        verdict = "identical" if identical else "differs in body"
        duplicates.append(
            f"{_DIALECT_DIR[dialect]} plsql {name}: {len(objs)} same-name units in one "
            f"dialect -- {verdict}; kept first, deduped"
        )


def _parse_dialect_plsql(
    src_root: Path,
    dialect: str,
    limit_modules: int | None,
    unparsed: list[str],
    plsql_objects: list[PlsqlObject],
    plsql_sources: dict[str, list[str]],
) -> None:
    """Parse the dedicated `PLSQL_Objects/*.sql` files for a dialect, appending
    each unit to the shared `plsql_objects`/`plsql_sources` accumulators (which
    already hold the inline units found in the Product module files). Duplicate
    detection runs once, in `run()`, over the combined collection.
    """
    plsql_dir = src_root / _DIALECT_DIR[dialect] / "DBScripts" / "Product" / "PLSQL_Objects"

    for sql_file in _sql_files(plsql_dir, limit_modules):
        module = sql_file.stem
        text = sql_file.read_text()
        rel = f"{_DIALECT_DIR[dialect]}/DBScripts/Product/PLSQL_Objects/{sql_file.name}"

        with _capture_warnings("okfdbparse.parse_plsql") as warnings:
            parsed = parse_plsql(text, dialect)
        unparsed.extend(f"{rel}: {w}" for w in warnings)

        for obj in parsed:
            obj.module = module
            _record_source(plsql_sources, obj.name, rel)
            plsql_objects.append(obj)


def _ordered_plsql(
    seed_units: list[PlsqlObject],
    product_units: list[PlsqlObject],
    product_names: set[str],
) -> list[PlsqlObject]:
    """Combine one dialect's PL/SQL units with precedence by SOURCE TIER: a
    Product definition always beats a Seed catalog's re-declaration of the same
    unit.

    Implemented by DROPPING Seed units whose name Product already declares,
    rather than by reordering. Reordering cannot express this: `reconcile.
    _merge_package_units` resolves a package's `module` first-wins but its
    spec/body last-wins, so no single ordering gives Product precedence for
    both. Dropping instead leaves `product_units` (Product-inline followed by
    the dedicated `PLSQL_Objects/` units) in its original order, so every
    previously-emitted card is byte-identical; the Seed units that survive are
    only those Product never declared -- purely additive new objects. The
    dropped unit's file is still recorded in `plsql_sources`, so an overlapping
    card still cites the Seed catalog that re-declares it.

    `product_names` is the union across BOTH dialects, which matters: a unit
    Product declares only in DB2 (so the card is `platform: [db2]`, module from
    the DB2 file) would otherwise have its *Oracle* side supplied by a Seed
    catalog -- and since `reconcile_plsql` builds the merged object on the
    Oracle one, the card's module would flip to that Seed module. Excluding
    cross-dialect keeps such a card exactly as it shipped.
    """
    seed_only = [obj for obj in seed_units if obj.name not in product_names]
    return product_units + seed_only


def run(src_root: Path, out_dir: Path, *, limit_modules: int | None = None) -> RunReport:
    """Parse+reconcile every WMOS table/PL/SQL object under `src_root`, emit
    one card per object under `out_dir/{tables,plsql}/` plus
    `out_dir/manifest.jsonl`, and return the `RunReport`.

    Raises `RunError` (after completing the full run) if the verification
    gate fails -- see module docstring.
    """
    unparsed: list[str] = []
    duplicates: list[str] = []
    unattached: list[str] = []
    sequence_names: list[str] = []

    # PL/SQL is collected from THREE places per dialect: inline units in the
    # Product module files and inline units in the Seed/Product catalogs (both
    # filled by _parse_dialect_tables, into separate buckets), plus the
    # dedicated PLSQL_Objects/ files (filled by _parse_dialect_plsql, appended
    # after the Product-inline units). `_ordered_plsql` then orders the buckets
    # by source tier for reconcile's LAST-wins union; duplicate detection runs
    # once on the combined result below.
    oracle_plsql: list[PlsqlObject] = []
    oracle_seed_plsql: list[PlsqlObject] = []
    oracle_plsql_sources: dict[str, list[str]] = {}
    db2_plsql: list[PlsqlObject] = []
    db2_seed_plsql: list[PlsqlObject] = []
    db2_plsql_sources: dict[str, list[str]] = {}

    oracle_tables, oracle_table_sources = _parse_dialect_tables(
        src_root, "oracle", limit_modules, unparsed, duplicates, unattached, sequence_names,
        oracle_plsql, oracle_plsql_sources, oracle_seed_plsql,
    )
    db2_tables, db2_table_sources = _parse_dialect_tables(
        src_root, "db2", limit_modules, unparsed, duplicates, unattached, sequence_names,
        db2_plsql, db2_plsql_sources, db2_seed_plsql,
    )
    merged_tables = reconcile_tables(oracle_tables, db2_tables)
    for table in merged_tables:
        table.source_files = _union_sources(
            oracle_table_sources, db2_table_sources, name=table.name
        )

    # Attach sequences AFTER reconcile, against the complete merged table set.
    # A sequence owner is resolved by name, and most DB2 sequence owners exist
    # only in the merged set (the DB2 dialect barely parses -- `!`-terminated
    # files sqlglot can't split -- so db2_tables is nearly empty; the merged set
    # carries every table name from the Oracle side). Orphans (no owner found)
    # are the non-fatal, reported kind.
    merged_by_name = {t.name: t for t in merged_tables}
    with _capture_warnings("okfdbparse.aux_unattached") as seq_unattached:
        for seq_name in sequence_names:
            _attach_sequence(merged_by_name, seq_name)
    unattached.extend(f"sequence: {w}" for w in seq_unattached)

    _parse_dialect_plsql(
        src_root, "oracle", limit_modules, unparsed, oracle_plsql, oracle_plsql_sources
    )
    _parse_dialect_plsql(
        src_root, "db2", limit_modules, unparsed, db2_plsql, db2_plsql_sources
    )
    # Union across dialects -- see `_ordered_plsql` on why cross-dialect matters.
    product_plsql_names = {o.name for o in oracle_plsql} | {o.name for o in db2_plsql}
    oracle_all_plsql = _ordered_plsql(oracle_seed_plsql, oracle_plsql, product_plsql_names)
    db2_all_plsql = _ordered_plsql(db2_seed_plsql, db2_plsql, product_plsql_names)
    _detect_plsql_duplicates(oracle_all_plsql, "oracle", duplicates)
    _detect_plsql_duplicates(db2_all_plsql, "db2", duplicates)

    merged_plsql = reconcile_plsql(oracle_all_plsql, db2_all_plsql)
    for obj in merged_plsql:
        obj.source_files = _union_sources(oracle_plsql_sources, db2_plsql_sources, name=obj.name)

    report = RunReport(unparsed=unparsed, duplicates=duplicates, unattached=unattached)
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

    # Deduped same-dialect same-name duplicates are visible but non-fatal:
    # record them in conflicts.log (written whenever any exist) so nothing is
    # silent, then let the run succeed.
    if report.duplicates:
        with (out_dir / "conflicts.log").open("w") as fh:
            for line in report.duplicates:
                fh.write(line + "\n")

    # Aux statements that parsed but had nowhere to attach (target table not in
    # the carded corpus, or an orphan sequence). A scope consequence rather than
    # a parser gap, so -- like conflicts.log -- fully visible, never silent, but
    # never fatal.
    if report.unattached:
        with (out_dir / "unattached.log").open("w") as fh:
            for line in report.unattached:
                fh.write(line + "\n")

    if report.unparsed:
        raise RunError(
            f"okfdbparse: {len(report.unparsed)} unparsed statement(s)/unit(s) "
            f"(never silently skipped): {report.unparsed}"
        )
    for kind, counts in report.counts.items():
        if counts["parsed"] != counts["emitted"]:
            raise RunError(
                f"okfdbparse: emitted count != parsed count for {kind!r}: {counts}"
            )

    return report


def main(argv: list[str] | None = None) -> int:
    # sqlglot logs a WARNING for every statement it degrades to a `Command`
    # (PL/SQL bodies, EXECUTE IMMEDIATE, `CREATE OR REPLACE SYNONYM ... FOR &1..x`,
    # etc.). `apply_aux` and `parse_plsql` handle `Command` nodes by design, so
    # this is pure noise -- and over the large Seed/Product catalogs it explodes
    # into hundreds of thousands of lines, whose disk I/O dominates the run.
    # Silence it (correctness is unaffected; our own gate warnings are separate).
    logging.getLogger("sqlglot").setLevel(logging.ERROR)

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
                "duplicates": report.duplicates,
                "unattached": len(report.unattached),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

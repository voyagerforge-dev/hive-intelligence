import pytest
from pathlib import Path

from okfdbparse.run import RunError, run


def _write(p: Path, s: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s)


def test_end_to_end_emits_cards_manifest_and_counts_match(tmp_path):
    src = tmp_path / "src"
    _write(
        src / "Oracle/DBScripts/Product/DOM.sql",
        'CREATE TABLE "T" ("A" NUMBER(1,0), PRIMARY KEY ("A"));\n'
        "comment on table T is 'demo';\n",
    )
    _write(src / "DB2/DBScripts/Product/DOM.sql", 'CREATE TABLE "T" ("A" SMALLINT);\n')
    out = tmp_path / "out"
    rep = run(src, out)
    assert (out / "tables/T.md").exists() and (out / "manifest.jsonl").exists()
    assert rep.counts["table"]["parsed"] == rep.counts["table"]["emitted"] == 1
    assert rep.unparsed == []


def test_gate_fails_on_unparsed_object(tmp_path):
    src = tmp_path / "src"
    _write(src / "Oracle/DBScripts/Product/BAD.sql", "CREATE TABLE (((( totally broken ;\n")
    with pytest.raises(RunError):
        run(src, tmp_path / "out")


def test_end_to_end_with_plsql_unit_both_dialects(tmp_path):
    src = tmp_path / "src"
    _write(
        src / "Oracle/DBScripts/Product/PLSQL_Objects/SHIP_CONFIRM.sql",
        "CREATE OR REPLACE PROCEDURE ship_confirm(p_id IN NUMBER) AS\n"
        "BEGIN\n"
        "  UPDATE shipment SET status = 'S' WHERE id = p_id;\n"
        "END;\n"
        "/\n",
    )
    _write(
        src / "DB2/DBScripts/Product/PLSQL_Objects/SHIP_CONFIRM.sql",
        "CREATE OR REPLACE PROCEDURE ship_confirm(p_id IN NUMBER) AS\n"
        "BEGIN\n"
        "  UPDATE shipment SET status = 'S' WHERE id = p_id;\n"
        "END;\n"
        "/\n",
    )
    out = tmp_path / "out"
    rep = run(src, out)
    assert rep.counts["plsql"]["parsed"] == rep.counts["plsql"]["emitted"] == 1
    card = (out / "plsql/ship_confirm.md").read_text()
    # sources: must point at the real per-object PLSQL_Objects file, not a
    # synthesized "<module>.sql" (module here would wrongly be "ship_confirm"
    # too, but the filename is uppercase -- proves the real path is threaded).
    assert "PLSQL_Objects/SHIP_CONFIRM.sql" in card


def test_skips_seed_archive_upgrade_createschema_directories(tmp_path):
    src = tmp_path / "src"
    _write(src / "Oracle/DBScripts/Product/DOM.sql", 'CREATE TABLE "T" ("A" NUMBER(1,0));\n')
    # a malformed statement tucked into a directory that must NEVER be walked
    _write(src / "Oracle/DBScripts/Product/Seed/SEED.sql", "CREATE TABLE (((( broken ;\n")
    _write(src / "Oracle/DBScripts/Product/Archive/OLD.sql", "CREATE TABLE (((( broken ;\n")
    _write(src / "Oracle/DBScripts/Product/Upgrade/PATCH.sql", "CREATE TABLE (((( broken ;\n")
    _write(src / "Oracle/DBScripts/Product/CreateSchema/SCHEMA.sql", "CREATE TABLE (((( broken ;\n")
    out = tmp_path / "out"
    rep = run(src, out)
    assert rep.unparsed == []
    assert rep.counts["table"]["parsed"] == rep.counts["table"]["emitted"] == 1


def test_gate_fails_on_malformed_plsql_unit(tmp_path):
    # A CREATE OR REPLACE unit with a typo'd kind keyword (PROCEEDURE) matches
    # no known PL/SQL kind, so parse_plsql captures no unit -- it must NOT be
    # dropped silently: the gate has to raise.
    src = tmp_path / "src"
    _write(
        src / "Oracle/DBScripts/Product/PLSQL_Objects/BROKEN.sql",
        "CREATE OR REPLACE PROCEEDURE broken(p IN NUMBER) AS\nBEGIN\n  NULL;\nEND;\n/\n",
    )
    with pytest.raises(RunError):
        run(src, tmp_path / "out")


def test_gate_fails_on_same_dialect_same_name_table_collision(tmp_path):
    # Two Oracle files each defining CREATE TABLE T: first-file-wins silently
    # discards the second definition -- the gate must catch the collision.
    src = tmp_path / "src"
    _write(src / "Oracle/DBScripts/Product/AAA.sql", 'CREATE TABLE "T" ("A" NUMBER(1,0));\n')
    _write(src / "Oracle/DBScripts/Product/BBB.sql", 'CREATE TABLE "T" ("B" NUMBER(1,0));\n')
    with pytest.raises(RunError):
        run(src, tmp_path / "out")


def test_gate_fails_on_same_dialect_same_name_plsql_collision(tmp_path):
    # Two distinct procedures named the same in one dialect (NOT a package
    # spec/body pair) -- must fail the gate.
    src = tmp_path / "src"
    _write(
        src / "Oracle/DBScripts/Product/PLSQL_Objects/A.sql",
        "CREATE OR REPLACE PROCEDURE dup(p IN NUMBER) AS\nBEGIN\n  NULL;\nEND;\n/\n",
    )
    _write(
        src / "Oracle/DBScripts/Product/PLSQL_Objects/B.sql",
        "CREATE OR REPLACE PROCEDURE dup(p IN NUMBER) AS\nBEGIN\n  NULL;\nEND;\n/\n",
    )
    with pytest.raises(RunError):
        run(src, tmp_path / "out")


def test_package_spec_and_body_across_files_is_not_a_collision(tmp_path):
    # A package spec + body (two same-name kind=package units in one dialect,
    # here even in separate files) is a LEGITIMATE merge -- must NOT be flagged
    # as a collision, and both files must appear in the card's sources.
    src = tmp_path / "src"
    _write(
        src / "Oracle/DBScripts/Product/PLSQL_Objects/DOM_ALLOC_SPEC.sql",
        "CREATE OR REPLACE PACKAGE dom_alloc AS\n"
        "  PROCEDURE allocate(p IN NUMBER);\n"
        "END dom_alloc;\n/\n",
    )
    _write(
        src / "Oracle/DBScripts/Product/PLSQL_Objects/DOM_ALLOC_BODY.sql",
        "CREATE OR REPLACE PACKAGE BODY dom_alloc AS\n"
        "  PROCEDURE allocate(p IN NUMBER) IS\n  BEGIN\n    NULL;\n  END;\n"
        "END dom_alloc;\n/\n",
    )
    out = tmp_path / "out"
    rep = run(src, out)
    assert rep.collisions == []
    assert rep.counts["plsql"]["parsed"] == rep.counts["plsql"]["emitted"] == 1
    card = (out / "plsql/dom_alloc.md").read_text()
    assert "PLSQL_Objects/DOM_ALLOC_SPEC.sql" in card
    assert "PLSQL_Objects/DOM_ALLOC_BODY.sql" in card


def test_limit_modules_caps_files_processed(tmp_path):
    src = tmp_path / "src"
    _write(src / "Oracle/DBScripts/Product/AAA.sql", 'CREATE TABLE "A1" ("A" NUMBER(1,0));\n')
    _write(src / "Oracle/DBScripts/Product/BBB.sql", 'CREATE TABLE "A2" ("A" NUMBER(1,0));\n')
    out = tmp_path / "out"
    rep = run(src, out, limit_modules=1)
    assert rep.counts["table"]["parsed"] == rep.counts["table"]["emitted"] == 1

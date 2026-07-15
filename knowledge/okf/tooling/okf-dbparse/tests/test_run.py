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


def test_differing_same_dialect_same_name_tables_dedup_and_log_not_fatal(tmp_path):
    # Two Oracle files defining CREATE TABLE T with DIFFERENT columns: at worst
    # we card one of two near-identical defs -- NOT the silent-drop-of-unique-
    # content the gate guards. So dedup (keep first), note it in conflicts.log,
    # and DO NOT raise.
    src = tmp_path / "src"
    _write(src / "Oracle/DBScripts/Product/AAA.sql", 'CREATE TABLE "T" ("A" NUMBER(1,0));\n')
    _write(src / "Oracle/DBScripts/Product/BBB.sql", 'CREATE TABLE "T" ("B" NUMBER(1,0));\n')
    out = tmp_path / "out"
    rep = run(src, out)  # must NOT raise
    assert rep.counts["table"]["parsed"] == rep.counts["table"]["emitted"] == 1
    assert len(rep.duplicates) == 1 and "differs in columns/pk" in rep.duplicates[0]
    log = (out / "conflicts.log").read_text()
    assert "table T" in log and "differs in columns/pk" in log


def test_identical_same_dialect_same_name_tables_dedup_and_log_identical(tmp_path):
    # A shared table each module's deploy script re-declares identically
    # (same columns/pk; only tablespace differs, which the parser ignores):
    # deduped, logged as "identical", BOTH files listed as sources, no raise.
    src = tmp_path / "src"
    _write(
        src / "Oracle/DBScripts/Product/TLM.sql",
        'CREATE TABLE "SHARED" ("A" NUMBER(1,0), PRIMARY KEY ("A")) TABLESPACE TLM_TBS;\n',
    )
    _write(
        src / "Oracle/DBScripts/Product/CM.sql",
        'CREATE TABLE "SHARED" ("A" NUMBER(1,0), PRIMARY KEY ("A")) TABLESPACE CM_TBS;\n',
    )
    out = tmp_path / "out"
    rep = run(src, out)
    assert rep.counts["table"]["parsed"] == rep.counts["table"]["emitted"] == 1
    assert len(rep.duplicates) == 1 and "identical" in rep.duplicates[0]
    assert "identical" in (out / "conflicts.log").read_text()
    card = (out / "tables/SHARED.md").read_text()
    assert "Product/TLM.sql" in card and "Product/CM.sql" in card


def test_differing_same_dialect_same_name_plsql_dedup_and_log_not_fatal(tmp_path):
    # Two procedures named the same in one dialect (NOT a package spec/body
    # pair) with DIFFERING bodies -- deduped + logged, NOT fatal.
    src = tmp_path / "src"
    _write(
        src / "Oracle/DBScripts/Product/PLSQL_Objects/A.sql",
        "CREATE OR REPLACE PROCEDURE dup(p IN NUMBER) AS\nBEGIN\n  NULL;\nEND;\n/\n",
    )
    _write(
        src / "Oracle/DBScripts/Product/PLSQL_Objects/B.sql",
        "CREATE OR REPLACE PROCEDURE dup(p IN NUMBER) AS\n"
        "BEGIN\n  UPDATE t SET x = 1;\nEND;\n/\n",
    )
    out = tmp_path / "out"
    rep = run(src, out)  # must NOT raise
    assert rep.counts["plsql"]["parsed"] == rep.counts["plsql"]["emitted"] == 1
    assert len(rep.duplicates) == 1 and "differs in body" in rep.duplicates[0]
    assert "plsql dup" in (out / "conflicts.log").read_text()


def test_identical_same_dialect_same_name_plsql_dedup_and_log_identical(tmp_path):
    # Same procedure re-declared identically in two files of one dialect:
    # deduped, logged as "identical", no raise.
    src = tmp_path / "src"
    body = "CREATE OR REPLACE PROCEDURE dup(p IN NUMBER) AS\nBEGIN\n  NULL;\nEND;\n/\n"
    _write(src / "Oracle/DBScripts/Product/PLSQL_Objects/A.sql", body)
    _write(src / "Oracle/DBScripts/Product/PLSQL_Objects/B.sql", body)
    out = tmp_path / "out"
    rep = run(src, out)
    assert rep.counts["plsql"]["parsed"] == rep.counts["plsql"]["emitted"] == 1
    assert len(rep.duplicates) == 1 and "identical" in rep.duplicates[0]


def test_package_spec_and_body_across_files_is_not_a_duplicate(tmp_path):
    # A package spec + body (two same-name kind=package units in one dialect,
    # here even in separate files) is a LEGITIMATE merge -- NOT a duplicate,
    # no conflicts.log entry, and both files appear in the card's sources.
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
    assert rep.duplicates == []
    assert not (out / "conflicts.log").exists()
    assert rep.counts["plsql"]["parsed"] == rep.counts["plsql"]["emitted"] == 1
    card = (out / "plsql/dom_alloc.md").read_text()
    assert "PLSQL_Objects/DOM_ALLOC_SPEC.sql" in card
    assert "PLSQL_Objects/DOM_ALLOC_BODY.sql" in card


def test_module_file_inline_triggers_and_views_are_carded(tmp_path):
    # A Product module file carries inline PL/SQL (triggers/views) alongside
    # its CREATE TABLEs. The runner must card the table AND each inline unit
    # (from the SAME file), with the module file as the unit's source.
    src = tmp_path / "src"
    _write(
        src / "Oracle/DBScripts/Product/WM.sql",
        'CREATE TABLE "T" ("A" NUMBER(1,0), PRIMARY KEY ("A"));\n'
        "\n"
        "CREATE OR REPLACE TRIGGER trg\n"
        "BEFORE INSERT ON T\n"
        "BEGIN\n"
        "  :NEW.A := 1;\n"
        "END;\n"
        "/\n"
        "\n"
        "CREATE OR REPLACE VIEW v AS SELECT A FROM T;\n",
    )
    out = tmp_path / "out"
    rep = run(src, out)
    assert rep.unparsed == []
    assert (out / "tables/T.md").exists()
    assert (out / "plsql/trg.md").exists()
    assert (out / "plsql/v.md").exists()
    assert rep.counts["table"]["parsed"] == rep.counts["table"]["emitted"] == 1
    assert rep.counts["plsql"]["parsed"] == rep.counts["plsql"]["emitted"] == 2
    # the trigger card carries the module file as source and its full body
    trg_card = (out / "plsql/trg.md").read_text()
    assert "Product/WM.sql" in trg_card
    assert ":NEW.A := 1;" in trg_card


def test_limit_modules_caps_files_processed(tmp_path):
    src = tmp_path / "src"
    _write(src / "Oracle/DBScripts/Product/AAA.sql", 'CREATE TABLE "A1" ("A" NUMBER(1,0));\n')
    _write(src / "Oracle/DBScripts/Product/BBB.sql", 'CREATE TABLE "A2" ("A" NUMBER(1,0));\n')
    out = tmp_path / "out"
    rep = run(src, out, limit_modules=1)
    assert rep.counts["table"]["parsed"] == rep.counts["table"]["emitted"] == 1


# --- Task 9 hardening: known-skip constructs must NOT trip the gate --------


def test_ctas_table_is_skipped_and_does_not_trip_the_gate(tmp_path):
    # Real construct: Oracle/DBScripts/Product/TCS.sql `item_cbo_gtt` -- a GTT
    # written as CTAS (no column list). Alongside a normal table in the same
    # file, so we also confirm the real table still parses/emits fine.
    src = tmp_path / "src"
    _write(
        src / "Oracle/DBScripts/Product/TCS.sql",
        'CREATE TABLE "REAL_TABLE" ("A" NUMBER(1,0));\n'
        "CREATE GLOBAL TEMPORARY TABLE item_cbo_gtt\n"
        "ON COMMIT DELETE ROWS\n"
        "AS SELECT * FROM item_cbo;\n",
    )
    out = tmp_path / "out"
    rep = run(src, out)
    assert rep.unparsed == []
    assert rep.counts["table"]["parsed"] == rep.counts["table"]["emitted"] == 1
    assert (out / "tables/REAL_TABLE.md").exists()
    assert not (out / "tables/item_cbo_gtt.md").exists()


def test_db2_variable_is_skipped_and_does_not_trip_the_gate(tmp_path):
    # Real construct: DB2/DBScripts/Product/PLSQL_Objects/
    # CA_Archive_Global_Variable.sql -- `!`-terminated global VARIABLE
    # declarations, alongside a real procedure in the same file.
    src = tmp_path / "src"
    _write(
        src / "DB2/DBScripts/Product/PLSQL_Objects/CA_Archive_Global_Variable.sql",
        "CREATE OR REPLACE VARIABLE VT_CONS_AGGREGATION VARCHAR(32000)!\n"
        "CREATE OR REPLACE PROCEDURE real_proc(p IN NUMBER) AS\n"
        "BEGIN\n"
        "  NULL;\n"
        "END;\n"
        "/\n",
    )
    out = tmp_path / "out"
    rep = run(src, out)
    assert rep.unparsed == []
    assert rep.counts["plsql"]["parsed"] == rep.counts["plsql"]["emitted"] == 1
    assert (out / "plsql/real_proc.md").exists()

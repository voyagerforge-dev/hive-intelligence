from hivedbparse.parse_plsql import parse_plsql

PKG = '''CREATE OR REPLACE PACKAGE dom_alloc AS
  PROCEDURE allocate(p_order IN NUMBER);  -- entry
END dom_alloc;
/
CREATE OR REPLACE PROCEDURE ship_confirm(p_id IN NUMBER) AS
BEGIN
  UPDATE shipment SET status = 'S' WHERE id = p_id;  -- note the ; inside
END;
/
'''


def test_splits_units_and_captures_full_body_verbatim():
    objs = {o.name.lower(): o for o in parse_plsql(PKG, "oracle")}
    assert set(objs) == {"dom_alloc", "ship_confirm"}
    assert objs["dom_alloc"].kind == "package"
    assert objs["ship_confirm"].kind == "procedure"
    # full body captured verbatim, including the inner ';' that would break a naive splitter
    assert "UPDATE shipment SET status = 'S'" in objs["ship_confirm"].body_oracle
    body = objs["ship_confirm"].body_oracle.strip()
    assert body.startswith("CREATE OR REPLACE PROCEDURE ship_confirm")
    assert objs["dom_alloc"].dialects == {"oracle"}
    # signature is the header up to AS/IS/BEGIN, not the whole body
    expected_sig = "CREATE OR REPLACE PROCEDURE ship_confirm(p_id IN NUMBER)"
    assert objs["ship_confirm"].signature == expected_sig


PKG_BODY = '''CREATE OR REPLACE PACKAGE BODY dom_alloc AS
  PROCEDURE allocate(p_order IN NUMBER) IS
  BEGIN
    NULL;
  END;
END dom_alloc;
/
'''


def test_package_body_is_a_distinct_unit_with_full_body():
    objs = parse_plsql(PKG_BODY, "oracle")
    assert len(objs) == 1
    body = objs[0]
    assert body.name.lower() == "dom_alloc"
    assert body.kind == "package"
    assert body.body_oracle.strip().startswith("CREATE OR REPLACE PACKAGE BODY dom_alloc")
    assert "PROCEDURE allocate" in body.body_oracle


# DB2-flavored PL/SQL: sqlglot 30.12 has no native "db2" dialect, so parse_plsql
# must map the logical "db2" label to a sqlglot dialect that exists (via the
# shared _sqlglot_dialect helper) rather than crashing on `dialect="db2"`.
DB2_TRIGGER = '''CREATE OR REPLACE TRIGGER trg_order_ins
BEFORE INSERT ON order_line
BEGIN
  UPDATE order_line SET note = 'inserted; ok' WHERE 1 = 1;
END;
/
'''


def test_db2_dialect_is_mapped_and_does_not_raise():
    objs = parse_plsql(DB2_TRIGGER, "db2")
    assert len(objs) == 1
    trg = objs[0]
    assert trg.name.lower() == "trg_order_ins"
    assert trg.kind == "trigger"
    assert trg.dialects == {"db2"}
    assert "UPDATE order_line SET note = 'inserted; ok'" in trg.body_db2
    assert trg.body_oracle == ""


# An arithmetic `/` (division) inside the body tokenizes as a SLASH just like the
# SQL*Plus terminator; only a `/` ALONE ON ITS OWN LINE terminates the unit, so
# everything after the division must survive in the captured body.
DIV = '''CREATE OR REPLACE PROCEDURE calc_avg(p IN NUMBER) AS
  v_avg NUMBER;
BEGIN
  v_avg := total / count;
  UPDATE t SET x = 1;
END;
/
'''


def test_arithmetic_division_slash_is_not_a_terminator():
    objs = parse_plsql(DIV, "oracle")
    assert len(objs) == 1
    body = objs[0].body_oracle
    # the division `/` must NOT truncate the body -- statements after it survive
    assert "v_avg := total / count;" in body
    assert "UPDATE t SET x = 1;" in body
    assert body.strip().endswith("END;")


# Schema-qualified object name: the dotted `schema.proc_name` must be captured
# whole, not truncated to just the schema.
QUALIFIED = '''CREATE OR REPLACE PROCEDURE app.calc(p IN NUMBER) AS
BEGIN
  NULL;
END;
/
'''


def test_schema_qualified_name_is_captured_whole():
    objs = parse_plsql(QUALIFIED, "oracle")
    assert len(objs) == 1
    assert objs[0].name == "app.calc"


# --- Real-corpus fixtures (BENCH Oracle/DB2 DDL) -- Task 9 hardening ---------
# Real snippet: Oracle/DBScripts/Product/PLSQL_Objects/ACCESSORIAL_RATE_VIEW.sql
# -- Oracle's `FORCE` view modifier sits between `CREATE OR REPLACE` and the
# `VIEW` keyword, so the kind-keyword match must skip past it.
FORCE_VIEW_REAL = '''CREATE OR REPLACE FORCE VIEW ACCESSORIAL_RATE_VIEW
(
   ACCESSORIAL_PARAM_SET_ID,
   ACCESSORIAL_RATE_ID,
   TC_COMPANY_ID
)
AS
SELECT ACCESSORIAL_PARAM_SET_ID, ACCESSORIAL_RATE_ID, TC_COMPANY_ID
FROM ACCESSORIAL_RATE
/
'''


def test_force_view_is_recognized_as_view_kind():
    # RED before the fix: `_match_kind` looks at the token right after `OR
    # REPLACE`, which is `FORCE` (a plain VAR), not `VIEW` -- the unit is
    # never found and the gate would flag it as an unrecognized PL/SQL unit.
    objs = parse_plsql(FORCE_VIEW_REAL, "oracle")
    assert len(objs) == 1
    view = objs[0]
    assert view.name == "ACCESSORIAL_RATE_VIEW"
    assert view.kind == "view"
    assert "SELECT ACCESSORIAL_PARAM_SET_ID" in view.body_oracle


# Real snippet: Oracle/DBScripts/Product/PLSQL_Objects/val_job_data_vw.sql --
# same `FORCE VIEW` modifier, but lowercase (`create or replace force view`).
FORCE_VIEW_LOWER_REAL = '''create or replace force view val_job_data_vw
(
    job_name, val_job_dtl_id, sql_id
)
as
select vjh.job_name, vjd.val_job_dtl_id, vjd.sql_id
from val_job_hdr vjh
join val_job_dtl vjd on vjd.val_job_hdr_id = vjh.val_job_hdr_id
/
'''


def test_force_view_lowercase_is_recognized_as_view_kind():
    objs = parse_plsql(FORCE_VIEW_LOWER_REAL, "oracle")
    assert len(objs) == 1
    assert objs[0].kind == "view"
    assert objs[0].name.lower() == "val_job_data_vw"


# Synthetic (not present in this corpus, but Oracle-legal and explicitly
# in scope): `NO FORCE`, `EDITIONABLE`, and `NONEDITIONABLE` view modifiers
# must be tolerated the same way as `FORCE`.
NO_FORCE_VIEW = '''CREATE OR REPLACE NO FORCE VIEW v1 AS SELECT 1 FROM DUAL
/
'''
EDITIONABLE_VIEW = '''CREATE OR REPLACE EDITIONABLE VIEW v2 AS SELECT 1 FROM DUAL
/
'''
NONEDITIONABLE_FORCE_VIEW = '''CREATE OR REPLACE NONEDITIONABLE FORCE VIEW v3 AS SELECT 1 FROM DUAL
/
'''


def test_no_force_editionable_nonEditionable_view_modifiers_are_tolerated():
    for sql, name in (
        (NO_FORCE_VIEW, "v1"),
        (EDITIONABLE_VIEW, "v2"),
        (NONEDITIONABLE_FORCE_VIEW, "v3"),
    ):
        objs = parse_plsql(sql, "oracle")
        assert len(objs) == 1, sql
        assert objs[0].kind == "view"
        assert objs[0].name == name


# Real snippet: DB2/DBScripts/Product/PLSQL_Objects/CA_Archive_Global_Variable.sql
# -- a DB2 global `VARIABLE` declaration (one per line, `!`-terminated, no
# `AS`/`IS`/`BEGIN` body at all). It's a known, deliberate NON-object
# construct (class 3): it must be recognized (not flagged as an unrecognized
# unit) and cleanly skipped -- no `PlsqlObject` emitted for it.
DB2_VARIABLE_REAL = (
    "CREATE OR REPLACE VARIABLE VT_CONS_AGGREGATION               VARCHAR(32000)!\n"
    "CREATE OR REPLACE VARIABLE VT_ADM                            VARCHAR(32000)!\n"
    "create or replace variable i_min integer default 1!\n"
)


def test_db2_variable_is_skipped_not_emitted():
    objs = parse_plsql(DB2_VARIABLE_REAL, "db2")
    assert objs == []


def test_db2_variable_skip_does_not_log_as_unrecognized(caplog):
    import logging

    caplog.set_level(logging.WARNING, logger="hivedbparse.parse_plsql")
    parse_plsql(DB2_VARIABLE_REAL, "db2")
    assert [r for r in caplog.records if r.name == "hivedbparse.parse_plsql"] == []


# Real snippet: DB2/DBScripts/Product/PLSQL_Objects/wm_archive_pkg.sql -- the
# same DB2 global VARIABLE construct, but `!`-terminated (bang) rather than
# `/`. Must skip just as cleanly as the `/`-terminated CA_Archive ones.
DB2_VARIABLE_BANG_REAL = (
    "create or replace variable c_arch_norm  char(1) default 'D' !\n"
    "create or replace variable c_arch_all   char(1) default 'Y'!\n"
    "create or replace variable gv_purge_code           varchar(3)!\n"
)


def test_db2_bang_terminated_variable_is_skipped(caplog):
    import logging

    caplog.set_level(logging.WARNING, logger="hivedbparse.parse_plsql")
    objs = parse_plsql(DB2_VARIABLE_BANG_REAL, "db2")
    assert objs == []
    assert [r for r in caplog.records if r.name == "hivedbparse.parse_plsql"] == []


# Real snippet: Oracle/DBScripts/Product/PLSQL_Objects/wm_unplan_pakd_order.sql
# -- a user-defined collection TYPE (`create or replace type t_num as table
# of number(9)`) sitting in the same file as a real procedure that must still
# parse. The TYPE is a known non-object construct (a helper collection type,
# not a documented schema object) -- KNOWN SKIP (class 3), not a failure.
TYPE_PLUS_PROC_REAL = '''create or replace type t_num as table of number(9)
/
create or replace procedure wm_unplan_pakd_order
(
    p_user_id       in user_profile.user_id%type,
    p_order_id      in orders.order_id%type
)
as
    va_order_list   t_num := t_num(p_order_id);
begin
    null;
end;
/
'''


def test_type_is_skipped_but_sibling_procedure_still_parses(caplog):
    import logging

    caplog.set_level(logging.WARNING, logger="hivedbparse.parse_plsql")
    objs = parse_plsql(TYPE_PLUS_PROC_REAL, "oracle")
    # the TYPE is skipped (not carded); the procedure survives
    assert [o.name for o in objs] == ["wm_unplan_pakd_order"]
    assert objs[0].kind == "procedure"
    # the skipped TYPE must NOT be flagged as an unrecognized unit
    assert [r for r in caplog.records if r.name == "hivedbparse.parse_plsql"] == []


# Real snippet: DB2/DBScripts/Product/PLSQL_Objects/wm_archive_pkg.sql -- the
# `!`-terminated DB2 array TYPE form (`create or replace type tIDs AS integer
# array[]!`). Same known-skip treatment.
DB2_TYPE_BANG_REAL = (
    "create or replace type tIDs AS                     integer array[]!\n"
    "create or replace type tvIDs AS                    varchar(50) array[]!\n"
)


def test_db2_array_type_is_skipped(caplog):
    import logging

    caplog.set_level(logging.WARNING, logger="hivedbparse.parse_plsql")
    objs = parse_plsql(DB2_TYPE_BANG_REAL, "db2")
    assert objs == []
    assert [r for r in caplog.records if r.name == "hivedbparse.parse_plsql"] == []


# `CREATE OR REPLACE TYPE BODY <name> AS ...` -- the body half of an Oracle
# object type; also a known skip (the type itself isn't carded, so neither is
# its body). Not present in this corpus, but in scope per the fix brief.
TYPE_BODY_SQL = '''CREATE OR REPLACE TYPE BODY my_type AS
  MEMBER FUNCTION f RETURN NUMBER IS BEGIN RETURN 1; END;
END;
/
'''


def test_type_body_is_skipped(caplog):
    import logging

    caplog.set_level(logging.WARNING, logger="hivedbparse.parse_plsql")
    objs = parse_plsql(TYPE_BODY_SQL, "oracle")
    assert objs == []
    assert [r for r in caplog.records if r.name == "hivedbparse.parse_plsql"] == []


# Inline module-file constructs: triggers/views are frequently declared with a
# BARE `CREATE` (no `OR REPLACE`). Both forms must be recognized as units --
# while `CREATE TABLE`/`CREATE INDEX`/`CREATE SEQUENCE` must NOT be.
BARE_TRIGGER_AND_VIEW = '''CREATE TABLE T (A NUMBER(1,0));

CREATE TRIGGER trg
BEFORE INSERT ON T
BEGIN
  NULL;
END;
/

CREATE VIEW v AS SELECT A FROM T;
'''


def test_bare_create_trigger_and_view_are_units_table_is_not():
    objs = {o.name.lower(): o for o in parse_plsql(BARE_TRIGGER_AND_VIEW, "oracle")}
    # the bare CREATE TABLE is NOT a PL/SQL unit; the bare trigger + view are
    assert set(objs) == {"trg", "v"}
    assert objs["trg"].kind == "trigger"
    assert objs["v"].kind == "view"
    assert objs["trg"].body_oracle.strip().startswith("CREATE TRIGGER trg")
    assert "NULL;" in objs["trg"].body_oracle


# A CREATE TABLE immediately followed by a CREATE OR REPLACE TRIGGER (the shape
# of a real Product module file): the table must not be captured by parse_plsql
# and the trigger must be, with its full body verbatim.
TABLE_THEN_TRIGGER = '''CREATE TABLE T (A NUMBER(1,0), B VARCHAR2(10));

CREATE OR REPLACE TRIGGER trg
BEFORE INSERT ON T
FOR EACH ROW
BEGIN
  :NEW.B := 'x';
END;
/
'''


def test_create_table_not_captured_and_trigger_body_is_verbatim():
    objs = parse_plsql(TABLE_THEN_TRIGGER, "oracle")
    assert len(objs) == 1
    trg = objs[0]
    assert trg.name.lower() == "trg" and trg.kind == "trigger"
    body = trg.body_oracle
    assert body.strip().startswith("CREATE OR REPLACE TRIGGER trg")
    assert ":NEW.B := 'x';" in body
    # the table declaration (which precedes the trigger) is not swallowed in
    assert "CREATE TABLE" not in body


# DB2 spells sequences with `OR REPLACE` (`CREATE OR REPLACE SEQUENCE`), and
# module files also carry `CREATE OR REPLACE SYNONYM x FOR y`. Neither is a
# PL/SQL unit we card -- sequences are handled table-side by parse_aux,
# synonyms are aliases -- so both must be recognized + skipped, NOT flagged as
# unrecognized units (which would trip the runner's unparsed gate).
SEQUENCE_AND_SYNONYM = (
    "CREATE OR REPLACE SEQUENCE SEQ_INV_COMMERCE_VIEW1 START WITH 1 INCREMENT BY 1;\n"
    "CREATE OR REPLACE SYNONYM my_syn FOR remote_tab@dblink;\n"
)


def test_sequence_and_synonym_are_skipped_not_unrecognized(caplog):
    import logging

    caplog.set_level(logging.WARNING, logger="hivedbparse.parse_plsql")
    objs = parse_plsql(SEQUENCE_AND_SYNONYM, "db2")
    assert objs == []
    # crucially: no WARNING -- so the runner never adds these to `unparsed`
    assert [r for r in caplog.records if r.name == "hivedbparse.parse_plsql"] == []


# A quoted identifier must yield a CLEAN name (no surrounding double-quotes),
# so downstream card_id/filename/title never carry `"..."`. parse_tables
# already strips quotes; parse_plsql must too.
QUOTED_VIEW = 'CREATE OR REPLACE VIEW "FOO_VW" AS SELECT 1 FROM DUAL\n/\n'
QUOTED_DOTTED_PROC = '''CREATE OR REPLACE PROCEDURE SCHEMA."FOO"(p IN NUMBER) AS
BEGIN
  NULL;
END;
/
'''


def test_quoted_unit_name_is_stripped_of_double_quotes():
    objs = parse_plsql(QUOTED_VIEW, "oracle")
    assert len(objs) == 1
    assert objs[0].name == "FOO_VW"  # not '"FOO_VW"'
    assert objs[0].kind == "view"


def test_quoted_dotted_name_strips_quotes_per_component():
    objs = parse_plsql(QUOTED_DOTTED_PROC, "oracle")
    assert len(objs) == 1
    assert objs[0].name == "SCHEMA.FOO"  # not 'SCHEMA."FOO"'


def test_db2_alias_and_nickname_recognized_and_skipped(caplog):
    import logging
    # DB2 spells synonyms as ALIAS / NICKNAME (with a `!` terminator). They must
    # be recognized as skip-kinds, not flagged as unrecognized units (gate fail).
    sql = (
        "CREATE OR REPLACE  ALIAS LOCN_HDR FOR TABLE SchemaName.LOCN_HDR!\n"
        "CREATE OR REPLACE NICKNAME SLOT_NN FOR REMOTE.SLOT!\n"
    )
    with caplog.at_level(logging.WARNING, logger="hivedbparse.parse_plsql"):
        units = parse_plsql(sql, "db2")
    assert units == []
    assert not any("unrecognized" in r.getMessage().lower() for r in caplog.records)

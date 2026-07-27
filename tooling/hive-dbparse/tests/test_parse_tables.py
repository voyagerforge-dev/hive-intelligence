from hivedbparse.parse_tables import parse_tables

ORA = '''
CREATE TABLE "MASTER_STAGING_DATA"
(
EVENT_ID       NUMBER(20,0),
EVENT_TYPE     VARCHAR2(15)  NOT NULL,  -- syscode ID
CREATED_DTTM   TIMESTAMP(6) NOT NULL,
PRIMARY KEY ("EVENT_ID"))
TABLESPACE DOM_DT_TBS;
'''


def test_parses_columns_types_notnull_and_pk():
    tabs = parse_tables(ORA, "oracle")
    assert set(tabs) == {"MASTER_STAGING_DATA"}
    t = tabs["MASTER_STAGING_DATA"]
    cols = {c.name: c for c in t.columns}
    assert cols["EVENT_ID"].type_oracle == "NUMBER(20, 0)"  # sqlglot normalizes spacing
    assert cols["EVENT_TYPE"].type_oracle == "VARCHAR2(15)"
    assert cols["EVENT_TYPE"].not_null is True
    assert cols["EVENT_ID"].not_null is False
    assert t.pk == ["EVENT_ID"]
    assert t.dialects == {"oracle"}


def test_nested_parens_and_inline_comment_do_not_break_parse():
    # a naive regex would mis-split on the inline "--" comment / the (20,0) parens
    tabs = parse_tables(ORA, "oracle")
    assert len(tabs["MASTER_STAGING_DATA"].columns) == 3


# A CREATE TABLE with no trailing storage clause -- sqlglot parses the whole
# statement directly into exp.Create (the fragment fallback is NOT exercised here).
ORA_NO_TAIL = '''
CREATE TABLE ORDER_LINE
(
ORDER_ID   NUMBER(20,0) NOT NULL,
LINE_NO    NUMBER(10,0),
PRIMARY KEY ("ORDER_ID"));
'''


def test_direct_ast_parse_without_storage_tail():
    tabs = parse_tables(ORA_NO_TAIL, "oracle")
    t = tabs["ORDER_LINE"]
    cols = {c.name: c for c in t.columns}
    assert set(cols) == {"ORDER_ID", "LINE_NO"}
    assert cols["ORDER_ID"].type_oracle == "NUMBER(20, 0)"
    assert cols["ORDER_ID"].not_null is True
    assert cols["LINE_NO"].not_null is False
    assert t.pk == ["ORDER_ID"]


# DB2-flavored DDL: sqlglot 30.12 has no native "db2" dialect, so parse_tables
# must map the logical "db2" label to a sqlglot dialect that exists. The trailing
# `IN <tablespace>` (DB2's tablespace clause) exercises the token-based fallback.
DB2 = '''
CREATE TABLE MASTER_STAGING_DATA
(
EVENT_ID       INTEGER NOT NULL,
EVENT_SEQ      DECIMAL(20,0),
EVENT_TYPE     VARCHAR(15) NOT NULL,
PRIMARY KEY (EVENT_ID))
IN DOM_DT_TBS;
'''


# --- Real-corpus fixtures (WMOS Oracle/DB2 DDL) -- Task 9 hardening ---------
# Real snippet: Oracle/DBScripts/Product/CBO.sql, table RULES. Oracle's
# constraint-state suffix `ENABLE` (appended by the DB export tool after every
# `NOT NULL`) is not modeled by sqlglot's oracle grammar and must be tolerated
# without losing the actual `NOT NULL`.
RULES_REAL = '''
CREATE TABLE "RULES"
  (
    "RULES_ID" NUMBER(9,0) NOT NULL ENABLE,
    "RULE_TYPE"    VARCHAR2(3 CHAR),
    "CREATE_DATE_TIME" TIMESTAMP (6),
    "MOD_DATE_TIME" TIMESTAMP (6),
    "USER_ID"         VARCHAR2(50 CHAR),
    "RULES_DESC" VARCHAR2(40 CHAR),
    "VERSION_ID"   NUMBER(9,0) DEFAULT 1 NOT NULL ENABLE,
    "CREATED_DTTM" TIMESTAMP (6) DEFAULT SYSTIMESTAMP NOT NULL ENABLE,
    "LAST_UPDATED_DTTM" TIMESTAMP (6)
  )TABLESPACE CBO_TXN_DT_TBS;
'''


def test_not_null_enable_is_tolerated():
    # RED before the fix: sqlglot's oracle grammar rejects the trailing
    # `ENABLE` and the fragment fallback (same broken text) fails too.
    tabs = parse_tables(RULES_REAL, "oracle")
    assert set(tabs) == {"RULES"}
    cols = {c.name: c for c in tabs["RULES"].columns}
    assert cols["RULES_ID"].not_null is True
    assert cols["RULES_ID"].type_oracle == "NUMBER(9, 0)"
    assert cols["VERSION_ID"].not_null is True
    assert cols["RULE_TYPE"].not_null is False


# Real snippet: Oracle/DBScripts/Product/CBO.sql, table RULE_PARM -- a second
# NOT NULL ENABLE table, this one with a DEFAULT interleaved before NOT NULL
# ENABLE, plus the trailing TABLESPACE tail (exercises fragment fallback too).
RULE_PARM_REAL = '''
CREATE TABLE "RULE_PARM"
  (
    "RULE_PARM_ID"          NUMBER(9,0) NOT NULL ENABLE,
    "VERSION_ID"             NUMBER(9,0) DEFAULT 1 NOT NULL ENABLE,
    "RULE_ID"                NUMBER(9,0) NOT NULL ENABLE,
    "RULE_PRTY"                 NUMBER(5,0) DEFAULT 0 NOT NULL ENABLE,
    "CREATE_DATE_TIME" TIMESTAMP (6),
    "MOD_DATE_TIME" TIMESTAMP (6),
    "CREATED_DTTM" TIMESTAMP (6) DEFAULT SYSTIMESTAMP NOT NULL ENABLE,
    "LAST_UPDATED_DTTM" TIMESTAMP (6),
    "USER_ID"                   VARCHAR2(50 CHAR),
    "RULE_HDR_ID"               NUMBER(9,0),
    "RULES_ID"        NUMBER(9,0) NOT NULL ENABLE
  )TABLESPACE CBO_TXN_DT_TBS;
'''


def test_not_null_enable_with_default_and_tablespace_tail():
    tabs = parse_tables(RULE_PARM_REAL, "oracle")
    assert set(tabs) == {"RULE_PARM"}
    cols = {c.name: c for c in tabs["RULE_PARM"].columns}
    assert len(cols) == 11
    assert cols["RULE_PARM_ID"].not_null is True
    assert cols["RULE_HDR_ID"].not_null is False


# Real snippet: Oracle/DBScripts/Product/SCPP.sql, tables MMC_AUDIT_HDR/DTL --
# a TABLE-LEVEL (not column-level) `CONSTRAINT ... PRIMARY KEY (...) ENABLE`
# and `... FOREIGN KEY (...) REFERENCES ... ENABLE`: here `ENABLE` trails a
# `)` rather than `NOT NULL`, so the fix must not assume NOT NULL precedes it.
MMC_AUDIT_DTL_REAL = '''
CREATE TABLE MMC_AUDIT_DTL
(
    MMC_AUDIT_DTL_ID   NUMBER NOT NULL,
    MMC_AUDIT_HDR_ID   NUMBER NOT NULL,
    JOB_NAME           VARCHAR2 (50) NOT NULL,
    TABLE_NAME         VARCHAR2 (64) NOT NULL,
    FUNCTION_GROUP     VARCHAR2 (64) NOT NULL,
    EXP_ROWS           NUMBER,
    INS_ROWS           NUMBER,
    UPD_ROWS           NUMBER,
    DEL_ROWS           NUMBER,
    FILE_COUNT         NUMBER,
    STATUS             INT DEFAULT 0 NOT NULL,
    CREATE_DATE_TIME   TIMESTAMP,
    MOD_DATE_TIME      TIMESTAMP,
    USERNAME           VARCHAR2 (50),
    CONSTRAINT MMC_AUDIT_DTL_ID_PK1 PRIMARY KEY (MMC_AUDIT_DTL_ID) ENABLE,
    CONSTRAINT MMC_AUDIT_HDR_ID_FK1 FOREIGN KEY (MMC_AUDIT_HDR_ID)
    REFERENCES MMC_AUDIT_HDR (MMC_AUDIT_HDR_ID)
    ENABLE
)
TABLESPACE LEMA_TXN_DT_TBS;
'''


def test_table_level_constraint_enable_is_tolerated():
    tabs = parse_tables(MMC_AUDIT_DTL_REAL, "oracle")
    assert set(tabs) == {"MMC_AUDIT_DTL"}
    t = tabs["MMC_AUDIT_DTL"]
    assert t.pk == ["MMC_AUDIT_DTL_ID"]
    assert len(t.columns) == 14


# Real snippet: Oracle/DBScripts/Product/EEM.sql, GLOBAL_ITEM_INVENTORY_GTT --
# `CREATE GLOBAL TEMPORARY TABLE` with `NOT NULL ENABLE` columns and a
# trailing `ON COMMIT PRESERVE ROWS` clause.
GTT_REAL = '''
CREATE GLOBAL TEMPORARY TABLE GLOBAL_ITEM_INVENTORY_GTT
 (TC_COMPANY_ID NUMBER(9,0) NOT NULL ENABLE,
 FACILITY_ID NUMBER(9,0) NOT NULL ENABLE,
 ITEM_ID NUMBER(19,0) NOT NULL ENABLE,
 QUANTITY_UOM_ID NUMBER(8,0) ,
 BUSINESS_PARTNER VARCHAR2(10 CHAR),
 ORDERED_TOTAL NUMBER,
 INBOUND_TOTAL NUMBER,
 ON_HAND_TOTAL NUMBER
 )ON COMMIT preserve ROWS;
'''


def test_global_temporary_table_with_not_null_enable_and_on_commit_tail():
    tabs = parse_tables(GTT_REAL, "oracle")
    assert set(tabs) == {"GLOBAL_ITEM_INVENTORY_GTT"}
    t = tabs["GLOBAL_ITEM_INVENTORY_GTT"]
    cols = {c.name: c for c in t.columns}
    assert len(cols) == 8
    assert cols["TC_COMPANY_ID"].not_null is True
    assert cols["QUANTITY_UOM_ID"].not_null is False


# Real snippet: Oracle/DBScripts/Product/TCS.sql -- a GTT written as CTAS
# (`CREATE GLOBAL TEMPORARY TABLE x ... AS SELECT ...`, no column list). This
# is a KNOWN SKIP (class 3): there's no column list to card, so it must not
# be emitted as a `Table` AND must not be reported as unparsed.
CTAS_GTT_REAL = '''
CREATE GLOBAL TEMPORARY TABLE item_cbo_gtt
ON COMMIT DELETE ROWS
AS SELECT * FROM item_cbo;
'''

# Real snippet: Oracle/DBScripts/Product/WM.sql -- an ordinary (non-GTT) CTAS.
CTAS_PLAIN_REAL = '''
CREATE TABLE COMPANY_PARAMETER_MIGR_WM
AS
    SELECT *
      FROM COMPANY_PARAMETER;
'''


def test_ctas_tables_are_skipped_not_unparsed(caplog):
    import logging

    caplog.set_level(logging.WARNING, logger="hivedbparse.parse_tables")
    tabs = parse_tables(CTAS_GTT_REAL + CTAS_PLAIN_REAL, "oracle")
    # no column list to card -- neither CTAS becomes a Table object ...
    assert tabs == {}
    # ... and neither is logged as an unparsed WARNING (a known, clean skip).
    assert [r for r in caplog.records if r.name == "hivedbparse.parse_tables"] == []


# Real snippet: Oracle/DBScripts/Product/CM.sql, FBL_FORMULA_DETAIL --
# `GENERATED ALWAYS AS IDENTITY` column (regression guard: sqlglot's oracle
# grammar already models this natively, confirmed still true post-fix).
IDENTITY_REAL = '''
CREATE TABLE FBL_FORMULA_DETAIL
(
   FORMULA_DETAIL_ID   NUMBER GENERATED ALWAYS AS IDENTITY NOT NULL,
FORMULA_ID NUMBER NOT NULL,
FORMULA_DEPENDENT_ID NUMBER NOT NULL,
CREATED_DTTM TIMESTAMP DEFAULT SYSTIMESTAMP,
UPDATED_DTTM TIMESTAMP DEFAULT SYSTIMESTAMP,
CREATED_SOURCE VARCHAR2(50),
UPDATED_SOURCE VARCHAR2(50)
)TABLESPACE CM_BST4K_DT_TBS;
'''


def test_generated_always_as_identity_column_is_tolerated():
    tabs = parse_tables(IDENTITY_REAL, "oracle")
    assert set(tabs) == {"FBL_FORMULA_DETAIL"}
    cols = {c.name: c for c in tabs["FBL_FORMULA_DETAIL"].columns}
    assert cols["FORMULA_DETAIL_ID"].not_null is True
    assert len(cols) == 7


# Real snippet: DB2/DBScripts/Product/POD.sql, DRIVER_SHIPMENT -- DB2's bare
# `CURRENT TIMESTAMP` special register (two words, no parens/underscore) used
# as a DEFAULT value; sqlglot's generic grammar (used for the DB2 logical
# dialect) only recognizes the underscored `CURRENT_TIMESTAMP` form.
DRIVER_SHIPMENT_REAL = '''
CREATE TABLE DRIVER_SHIPMENT
  (
    ROW_UID           DECIMAL(10,0) NOT NULL,
    DRIVER_ID         DECIMAL (12,0) NOT NULL,
    SHIPMENT_ID       DECIMAL (10,0) NOT NULL,
    CARRIER_ID        DECIMAL (10,0) NOT NULL,
    LAST_UPDATED_DTTM TIMESTAMP DEFAULT CURRENT TIMESTAMP NOT NULL
  ) IN APPT_TXN_DT_TBS INDEX IN APPT_TXN_IDX_TBS;
'''


def test_db2_bare_current_timestamp_default_is_tolerated():
    tabs = parse_tables(DRIVER_SHIPMENT_REAL, "db2")
    assert set(tabs) == {"DRIVER_SHIPMENT"}
    cols = {c.name: c for c in tabs["DRIVER_SHIPMENT"].columns}
    assert len(cols) == 5
    assert cols["LAST_UPDATED_DTTM"].not_null is True


# Real snippet: Oracle/DBScripts/Product/SCPP.sql -- CREATE SEQUENCE whose
# name happens to contain the substring "TABLE" (SEQ_XTABLE_ID). Must never be
# mistaken for a (failed) CREATE TABLE and logged as unparsed.
SEQUENCE_REAL = "CREATE SEQUENCE SEQ_XTABLE_ID START WITH 1 INCREMENT BY 1;\n"

# Real snippet: Oracle/DBScripts/Product/WM.sql -- CREATE OR REPLACE TYPE ...
# AS TABLE OF ... (an Oracle nested-table TYPE, not a table at all -- "TABLE"
# appears as a literal keyword deeper in the statement).
TYPE_AS_TABLE_REAL = "CREATE OR REPLACE TYPE t_num AS TABLE OF NUMBER (10);\n"

# Real snippet: Oracle/DBScripts/Product/TCS.sql -- CREATE MATERIALIZED VIEW
# ... TABLESPACE ... AS SELECT (the substring "TABLE" appears inside
# "TABLESPACE").
MATVIEW_REAL = (
    "Create Materialized View DOCK_MV TABLESPACE EP_BST4K_DT_TBS AS SELECT * from DOC;\n"
)


def test_non_table_creates_with_table_substring_are_not_flagged_unparsed(caplog):
    import logging

    caplog.set_level(logging.WARNING, logger="hivedbparse.parse_tables")
    tabs = parse_tables(SEQUENCE_REAL + TYPE_AS_TABLE_REAL + MATVIEW_REAL, "oracle")
    assert tabs == {}
    assert [r for r in caplog.records if r.name == "hivedbparse.parse_tables"] == []


# Real snippet: Oracle/DBScripts/Product/EEM.sql, table ROUTE -- table-level
# named constraints (`CONSTRAINT <name> PRIMARY KEY (...)` and `... UNIQUE
# (...)`) each carrying a `USING INDEX TABLESPACE ...` storage clause INSIDE
# the column-list parens (so the fragment fallback's paren-trim can't reach
# it), plus column `DEFAULT SYSTIMESTAMP`, leading-comma column style, and
# `TIMESTAMP (6)` (space before paren).
ROUTE_REAL = '''
CREATE TABLE ROUTE
(
  ROUTE_ID NUMBER
, ROUTE_NAME VARCHAR2(100) NOT NULL
, ROUTE_DESCRIPTION VARCHAR2(500) NOT NULL
, CREATED_DTTM TIMESTAMP (6) DEFAULT SYSTIMESTAMP NOT NULL
, LAST_UPDATED_DTTM TIMESTAMP (6) DEFAULT SYSTIMESTAMP NOT NULL
, TC_COMPANY_ID NUMBER(9,0) NOT NULL
, CONSTRAINT ROUTE_PK PRIMARY KEY (ROUTE_ID) USING INDEX TABLESPACE EP_BST4K_IDX_TBS
, CONSTRAINT ROUTE_UK1 UNIQUE (ROUTE_NAME, TC_COMPANY_ID) USING INDEX TABLESPACE EP_BST4K_IDX_TBS
) TABLESPACE EP_BST4K_DT_TBS;
'''


def test_table_level_constraint_using_index_tablespace_is_tolerated():
    # RED before the fix: the `USING INDEX TABLESPACE ...` after the PK/UNIQUE
    # constraint (inside the column-list parens) makes sqlglot reject the
    # statement, and the fragment fallback -- which only trims a trailing
    # storage clause OUTSIDE the parens -- can't help.
    tabs = parse_tables(ROUTE_REAL, "oracle")
    assert set(tabs) == {"ROUTE"}
    t = tabs["ROUTE"]
    cols = {c.name: c for c in t.columns}
    assert set(cols) == {
        "ROUTE_ID",
        "ROUTE_NAME",
        "ROUTE_DESCRIPTION",
        "CREATED_DTTM",
        "LAST_UPDATED_DTTM",
        "TC_COMPANY_ID",
    }
    assert cols["ROUTE_NAME"].not_null is True
    assert cols["CREATED_DTTM"].not_null is True  # DEFAULT SYSTIMESTAMP tolerated
    assert cols["ROUTE_ID"].not_null is False
    assert t.pk == ["ROUTE_ID"]


# Real snippet: Oracle/DBScripts/Product/LM.sql, table E_OBS_INT -- the
# `CONSTRAINT ... PRIMARY KEY` and its `(cols) USING INDEX TABLESPACE ...`
# span two lines (the clause wraps), exercising the same fix.
E_OBS_INT_REAL = '''
CREATE TABLE E_OBS_INT
(
   INT_TYPE_ID        NUMBER (9),
   INT_TYPE           VARCHAR2 (15),
   DESCRIPTION        VARCHAR2 (30),
   WHSE               VARCHAR2 (3),
   SYS_CREATED        CHAR (1),
   CREATE_DATE_TIME   DATE,
   MOD_DATE_TIME      DATE,
   VERSION_ID         NUMBER (6),
   CONSTRAINT E_OBS_INT_PK PRIMARY KEY
      (INT_TYPE_ID) USING INDEX TABLESPACE LM_IDX_TBS
) TABLESPACE LM_TXN4K_TBS;
'''


def test_table_level_constraint_using_index_multiline_is_tolerated():
    tabs = parse_tables(E_OBS_INT_REAL, "oracle")
    assert set(tabs) == {"E_OBS_INT"}
    t = tabs["E_OBS_INT"]
    assert len(t.columns) == 8
    assert t.pk == ["INT_TYPE_ID"]


def test_db2_dialect_parses_without_crash():
    # RED before the logical->sqlglot mapping: this raised
    # ValueError("Unknown dialect 'db2'") on the first statement.
    tabs = parse_tables(DB2, "db2")
    assert set(tabs) == {"MASTER_STAGING_DATA"}
    t = tabs["MASTER_STAGING_DATA"]
    cols = {c.name: c for c in t.columns}
    assert len(cols) == 3
    # types are tagged on type_db2 (logical label), not type_oracle
    assert cols["EVENT_SEQ"].type_db2 == "DECIMAL(20, 0)"
    assert cols["EVENT_TYPE"].type_db2 == "VARCHAR(15)"
    assert cols["EVENT_ID"].type_oracle is None
    assert cols["EVENT_TYPE"].not_null is True
    assert cols["EVENT_SEQ"].not_null is False
    assert t.pk == ["EVENT_ID"]
    assert t.dialects == {"db2"}


def test_generated_always_as_identity_column_stripped():
    sql = (
        "CREATE TABLE ID_T\n"
        " ( ID NUMBER GENERATED ALWAYS AS IDENTITY MINVALUE 1 MAXVALUE 9999999999 "
        "INCREMENT BY 1 START WITH 1 CACHE 20 NOORDER  NOCYCLE  NOT NULL ENABLE,\n"
        "   A NUMBER(9,0),\n"
        "   CONSTRAINT PK_ID PRIMARY KEY (ID) );"
    )
    r = parse_tables(sql, "oracle")
    assert "ID_T" in r
    cols = {c.name: c.type_oracle for c in r["ID_T"].columns}
    assert cols["ID"] == "NUMBER"
    assert cols["A"] == "NUMBER(9, 0)"


def test_legacy_long_and_long_raw_types_mapped():
    sql = "CREATE TABLE LR_T ( H NUMBER(9,0), REC LONG RAW, NOTES LONG );"
    r = parse_tables(sql, "oracle")
    cols = {c.name: c.type_oracle for c in r["LR_T"].columns}
    assert cols["REC"] == "BLOB"
    assert cols["NOTES"] == "CLOB"

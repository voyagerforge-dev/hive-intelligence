from okfdbparse.parse_tables import parse_tables

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

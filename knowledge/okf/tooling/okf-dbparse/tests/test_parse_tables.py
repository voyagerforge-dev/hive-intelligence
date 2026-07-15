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

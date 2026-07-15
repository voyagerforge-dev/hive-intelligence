from okfdbparse.parse_plsql import parse_plsql

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

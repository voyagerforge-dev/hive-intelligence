from okfdbparse.model import Column, PlsqlObject, Table
from okfdbparse.parse_plsql import parse_plsql
from okfdbparse.reconcile import reconcile_plsql, reconcile_tables


def test_merges_types_by_name_and_flags_dialect_only():
    ora = {
        "T": Table(
            "T", "M", columns=[Column("A", type_oracle="NUMBER(20,0)")], dialects={"oracle"}
        )
    }
    db2 = {
        "T": Table(
            "T",
            "M",
            columns=[
                Column("A", type_db2="DECIMAL(20,0)"),
                Column("B", type_db2="VARCHAR(5)"),
            ],
            dialects={"db2"},
        ),
        "T2": Table("T2", "M", columns=[Column("X", type_db2="INTEGER")], dialects={"db2"}),
    }
    out = {t.name: t for t in reconcile_tables(ora, db2)}
    a = {c.name: c for c in out["T"].columns}
    assert a["A"].type_oracle == "NUMBER(20,0)" and a["A"].type_db2 == "DECIMAL(20,0)"
    assert a["B"].type_oracle is None and a["B"].type_db2 == "VARCHAR(5)"  # column only in DB2
    assert out["T"].dialects == {"oracle", "db2"}
    assert out["T2"].dialects == {"db2"}  # table only in DB2


def test_tables_reconcile_does_not_mutate_inputs():
    ora = {
        "T": Table(
            "T", "M", columns=[Column("A", type_oracle="NUMBER(20,0)")], dialects={"oracle"}
        )
    }
    db2 = {
        "T": Table("T", "M", columns=[Column("A", type_db2="DECIMAL(20,0)")], dialects={"db2"})
    }
    reconcile_tables(ora, db2)
    assert ora["T"].dialects == {"oracle"}
    assert ora["T"].columns[0].type_db2 is None
    assert db2["T"].dialects == {"db2"}


def test_oracle_authoritative_for_structure():
    ora = {
        "T": Table(
            "T",
            "M",
            comment="oracle comment",
            columns=[Column("A", type_oracle="NUMBER(20,0)")],
            pk=["A"],
            fks=[("A", "OTHER", "ID")],
            indexes=[("IX_T", ["A"], True)],
            dialects={"oracle"},
        )
    }
    db2 = {
        "T": Table(
            "T",
            "M",
            comment="db2 comment -- ignored",
            columns=[Column("A", type_db2="DECIMAL(20,0)")],
            pk=["SOMETHING_ELSE"],
            dialects={"db2"},
        )
    }
    out = {t.name: t for t in reconcile_tables(ora, db2)}
    t = out["T"]
    assert t.comment == "oracle comment"
    assert t.pk == ["A"]
    assert t.fks == [("A", "OTHER", "ID")]
    assert t.indexes == [("IX_T", ["A"], True)]


def test_plsql_union_by_name_and_dialect_flags():
    oracle = [
        PlsqlObject("PROC_A", "M", kind="procedure", body_oracle="BODY A", dialects={"oracle"})
    ]
    db2 = [PlsqlObject("PROC_B", "M", kind="procedure", body_db2="BODY B", dialects={"db2"})]
    out = {o.name: o for o in reconcile_plsql(oracle, db2)}
    assert set(out) == {"PROC_A", "PROC_B"}
    assert out["PROC_A"].dialects == {"oracle"}
    assert out["PROC_B"].dialects == {"db2"}


def test_plsql_identical_body_normalizes_whitespace_and_clears_db2():
    oracle = [
        PlsqlObject(
            "PROC_A",
            "M",
            kind="procedure",
            body_oracle="BEGIN\n  UPDATE t SET x = 1;\nEND;",
            dialects={"oracle"},
        )
    ]
    db2 = [
        PlsqlObject(
            "PROC_A",
            "M",
            kind="procedure",
            body_db2="BEGIN   UPDATE t SET x = 1;   END;",
            dialects={"db2"},
        )
    ]
    out = {o.name: o for o in reconcile_plsql(oracle, db2)}
    assert out["PROC_A"].dialects == {"oracle", "db2"}
    assert out["PROC_A"].body_db2 == ""  # renders "Identical to Oracle"
    assert out["PROC_A"].body_oracle == "BEGIN\n  UPDATE t SET x = 1;\nEND;"


def test_plsql_differing_body_keeps_both():
    oracle = [
        PlsqlObject(
            "PROC_A", "M", kind="procedure", body_oracle="BEGIN NULL; END;", dialects={"oracle"}
        )
    ]
    db2 = [
        PlsqlObject(
            "PROC_A",
            "M",
            kind="procedure",
            body_db2="BEGIN CALL SOMETHING(); END;",
            dialects={"db2"},
        )
    ]
    out = {o.name: o for o in reconcile_plsql(oracle, db2)}
    assert out["PROC_A"].body_oracle == "BEGIN NULL; END;"
    assert out["PROC_A"].body_db2 == "BEGIN CALL SOMETHING(); END;"


PKG_SPEC = """CREATE OR REPLACE PACKAGE dom_alloc AS
  PROCEDURE allocate(p_order IN NUMBER);  -- entry
END dom_alloc;
/
"""

PKG_BODY = """CREATE OR REPLACE PACKAGE BODY dom_alloc AS
  PROCEDURE allocate(p_order IN NUMBER) IS
  BEGIN
    NULL;
  END;
END dom_alloc;
/
"""


def test_package_spec_and_body_pair_collapses_to_one_object():
    # parse_plsql (Task 3) returns the spec and body as two separate
    # PlsqlObjects with the same name/kind="package" -- reconcile_plsql must
    # merge them into ONE object (spec text -> signature, body text -> body_oracle)
    # before doing any cross-dialect union, so exactly one card is emitted.
    spec_objs = parse_plsql(PKG_SPEC, "oracle")
    body_objs = parse_plsql(PKG_BODY, "oracle")
    oracle_units = spec_objs + body_objs

    out = reconcile_plsql(oracle_units, [])
    assert len(out) == 1
    pkg = out[0]
    assert pkg.name.lower() == "dom_alloc"
    assert pkg.kind == "package"
    assert pkg.signature.strip().startswith("CREATE OR REPLACE PACKAGE dom_alloc")
    assert "PACKAGE BODY" not in pkg.signature.upper()
    assert pkg.body_oracle.strip().startswith("CREATE OR REPLACE PACKAGE BODY dom_alloc")
    assert pkg.dialects == {"oracle"}


def test_package_spec_only_no_body_present():
    spec_objs = parse_plsql(PKG_SPEC, "oracle")
    out = reconcile_plsql(spec_objs, [])
    assert len(out) == 1
    pkg = out[0]
    assert pkg.signature.strip().startswith("CREATE OR REPLACE PACKAGE dom_alloc")
    assert pkg.body_oracle == ""


def test_package_body_only_no_spec_present():
    body_objs = parse_plsql(PKG_BODY, "oracle")
    out = reconcile_plsql(body_objs, [])
    assert len(out) == 1
    pkg = out[0]
    assert pkg.signature == ""
    assert pkg.body_oracle.strip().startswith("CREATE OR REPLACE PACKAGE BODY dom_alloc")


def test_package_merges_across_both_dialects():
    oracle_units = parse_plsql(PKG_SPEC, "oracle") + parse_plsql(PKG_BODY, "oracle")
    db2_units = parse_plsql(PKG_SPEC, "db2") + parse_plsql(PKG_BODY, "db2")

    out = reconcile_plsql(oracle_units, db2_units)
    assert len(out) == 1
    pkg = out[0]
    assert pkg.dialects == {"oracle", "db2"}
    # identical spec/body text on both sides (normalized whitespace) -> db2 body cleared
    assert pkg.body_db2 == ""
    assert pkg.body_oracle.strip().startswith("CREATE OR REPLACE PACKAGE BODY dom_alloc")

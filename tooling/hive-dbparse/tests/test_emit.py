import yaml

from hivedbparse.emit import card_id, manifest_line, plsql_card, table_card
from hivedbparse.model import Column, PlsqlObject, Table


def _frontmatter_dict(md: str) -> dict:
    """Parse the leading `---`-delimited YAML block the same way hive-serve does."""
    parts = md.split("---", 2)
    assert len(parts) >= 3, "card must have a --- ... --- frontmatter block"
    fm = yaml.safe_load(parts[1])
    assert isinstance(fm, dict)
    return fm


def test_table_card_has_frontmatter_columns_and_verbatim_comment():
    t = Table(
        "MASTER_STAGING_DATA",
        "DOM",
        comment="Stage inbound events",
        columns=[
            Column(
                "EVENT_ID",
                type_oracle="NUMBER(20,0)",
                type_db2="BIGINT",
                not_null=True,
                comment="Unique identifier of the event",
            )
        ],
        pk=["EVENT_ID"],
        dialects={"oracle", "db2"},
    )
    md = table_card(t, "widgets")
    assert "type: dbobject" in md and "kind: table" in md
    assert "description: Stage inbound events" in md
    assert (
        "| EVENT_ID | NUMBER(20,0) | BIGINT | NOT NULL | PK | Unique identifier of the event |"
        in md
    )
    assert card_id(t, "widgets") == "widgets/db/tables/MASTER_STAGING_DATA"
    assert manifest_line(t, "widgets")["description"] == "Stage inbound events"


def test_table_card_frontmatter_is_valid_yaml():
    t = Table(
        "T",
        "DOM",
        comment="Stage inbound events",
        columns=[Column("A", type_oracle="NUMBER(20,0)")],
        dialects={"oracle"},
    )
    fm = _frontmatter_dict(table_card(t, "widgets"))
    assert fm["type"] == "dbobject"
    assert fm["kind"] == "table"
    assert fm["product"] == "widgets"
    assert fm["module"] == "DOM"
    assert fm["platform"] == ["oracle"]


def test_table_card_platform_reflects_dialects_both():
    t = Table("T", "DOM", columns=[Column("A")], dialects={"oracle", "db2"})
    fm = _frontmatter_dict(table_card(t, "widgets"))
    assert fm["platform"] == ["oracle", "db2"]


def test_table_card_related_is_fk_target_ids_only():
    t = Table(
        "ORDER_LINE",
        "DOM",
        columns=[Column("SYS_CODE_ID")],
        fks=[("SYS_CODE_ID", "SYS_CODE", "CODE_ID")],
        dialects={"oracle"},
    )
    fm = _frontmatter_dict(table_card(t, "widgets"))
    assert fm["related"] == ["widgets/db/tables/SYS_CODE"]
    md = table_card(t, "widgets")
    assert "widgets/db/tables/SYS_CODE" in md


def test_table_card_no_comment_yields_empty_description_never_invented():
    t = Table("T", "DOM", comment="", columns=[Column("A")], dialects={"oracle"})
    fm = _frontmatter_dict(table_card(t, "widgets"))
    assert fm["description"] == ""
    assert manifest_line(t, "widgets")["description"] == ""


def test_table_card_pipe_in_comment_is_escaped_in_columns_table():
    t = Table(
        "T",
        "DOM",
        columns=[Column("A", comment="Values are A|B|C")],
        dialects={"oracle"},
    )
    md = table_card(t, "widgets")
    assert "A\\|B\\|C" in md
    # the raw, unescaped comment must not appear (it would break the table row)
    assert "| Values are A|B|C |" not in md


def test_table_card_comment_with_colon_stays_valid_yaml():
    t = Table(
        "T", "DOM", comment="Ratio: quantity per unit", columns=[Column("A")], dialects={"oracle"}
    )
    fm = _frontmatter_dict(table_card(t, "widgets"))
    assert fm["description"] == "Ratio: quantity per unit"


def test_table_card_column_missing_in_one_dialect_is_marked_not_blank():
    t = Table(
        "T",
        "DOM",
        columns=[Column("A", type_oracle="NUMBER(20,0)", type_db2=None)],
        dialects={"oracle", "db2"},
    )
    md = table_card(t, "widgets")
    # A blank cell would read as "no type recorded"; this says "not in this dialect".
    assert "| A | NUMBER(20,0) | n/a |" in md


def test_table_card_sections_render_pk_fk_index_sequence_trigger():
    t = Table(
        "T",
        "DOM",
        columns=[Column("A"), Column("B")],
        pk=["A"],
        fks=[("B", "OTHER", "ID")],
        indexes=[("IDX_T", ["A"], True)],
        sequences=["T_SEQ"],
        triggers=["TRG_T"],
        dialects={"oracle"},
    )
    md = table_card(t, "widgets")
    pk_section = md.split("## Primary key")[1].split("## Foreign keys")[0]
    assert "## Primary key" in md and "A" in pk_section
    assert "B → OTHER(ID)" in md
    assert "widgets/db/tables/OTHER" in md
    assert "IDX_T (A) [UNIQUE]" in md
    assert "T_SEQ" in md
    assert "TRG_T" in md and "widgets/db/plsql/TRG_T" in md


def test_table_card_empty_sections_render_none():
    t = Table("T", "DOM", columns=[Column("A")], dialects={"oracle"})
    md = table_card(t, "widgets")
    headings = ("## Primary key", "## Foreign keys", "## Indexes", "## Sequences", "## Triggers")
    for heading in headings:
        section = md.split(heading, 1)[1].lstrip("\n")
        assert section.startswith("none")


def test_plsql_card_signature_and_oracle_source():
    o = PlsqlObject(
        "DOM_ALLOC",
        "DOM",
        kind="package",
        signature="CREATE OR REPLACE PACKAGE dom_alloc AS ...",
        body_oracle="CREATE OR REPLACE PACKAGE BODY dom_alloc AS ... END;",
        dialects={"oracle"},
    )
    md = plsql_card(o, "widgets")
    fm = _frontmatter_dict(md)
    assert fm["type"] == "dbobject"
    assert fm["kind"] == "package"
    assert fm["platform"] == ["oracle"]
    assert "## Signature / spec" in md
    assert "CREATE OR REPLACE PACKAGE dom_alloc AS ..." in md
    assert "## Source (Oracle)" in md
    assert "CREATE OR REPLACE PACKAGE BODY dom_alloc AS ... END;" in md
    assert card_id(o, "widgets") == "widgets/db/plsql/DOM_ALLOC"


def test_plsql_card_omits_db2_body_when_identical():
    o = PlsqlObject(
        "DOM_ALLOC",
        "DOM",
        kind="procedure",
        signature="PROCEDURE dom_alloc",
        body_oracle="BEGIN NULL; END;",
        body_db2="",
        dialects={"oracle", "db2"},
    )
    md = plsql_card(o, "widgets")
    assert "## Source (DB2)" in md
    assert "Identical to Oracle." in md


def test_plsql_card_includes_db2_body_when_present():
    o = PlsqlObject(
        "DOM_ALLOC",
        "DOM",
        kind="procedure",
        signature="PROCEDURE dom_alloc",
        body_oracle="BEGIN NULL; END;",
        body_db2="BEGIN CALL SOMETHING(); END;",
        dialects={"oracle", "db2"},
    )
    md = plsql_card(o, "widgets")
    assert "## Source (DB2)" in md
    assert "BEGIN CALL SOMETHING(); END;" in md
    assert "Identical to Oracle." not in md


def test_plsql_comment_less_title_is_clean_and_description_empty():
    # No header comment: title must be just NAME (kind) -- NOT the raw
    # signature/CREATE text -- and description must be empty (search-field
    # hygiene). The full signature still lives in the card body.
    o = PlsqlObject(
        "LANE_DETAIL_VIEW",
        "DOM",
        kind="view",
        signature="CREATE OR REPLACE VIEW LANE_DETAIL_VIEW AS SELECT ...",
        body_oracle="CREATE OR REPLACE VIEW LANE_DETAIL_VIEW AS SELECT ...",
        dialects={"oracle"},
    )
    fm = _frontmatter_dict(plsql_card(o, "widgets"))
    assert fm["title"] == "LANE_DETAIL_VIEW (view)"
    assert fm["description"] == ""
    assert "CREATE OR REPLACE VIEW" not in fm["title"]
    ml = manifest_line(o, "widgets")
    assert ml["title"] == "LANE_DETAIL_VIEW (view)"
    assert ml["description"] == ""


def test_plsql_with_comment_title_uses_comment():
    o = PlsqlObject(
        "DOM_ALLOC",
        "DOM",
        kind="package",
        comment="Allocation engine",
        signature="CREATE OR REPLACE PACKAGE dom_alloc AS ...",
        dialects={"oracle"},
    )
    fm = _frontmatter_dict(plsql_card(o, "widgets"))
    assert fm["title"] == "DOM_ALLOC: Allocation engine"
    assert fm["description"] == "Allocation engine"


def test_manifest_line_shape_for_table_and_plsql():
    t = Table("T", "DOM", comment="purpose", columns=[Column("A")], dialects={"oracle"})
    o = PlsqlObject("P", "DOM", kind="procedure", comment="does a thing", dialects={"oracle"})
    ml_t = manifest_line(t, "widgets")
    ml_o = manifest_line(o, "widgets")
    assert set(ml_t) == {"id", "kind", "module", "product", "title", "description", "tags"}
    assert ml_t["id"] == "widgets/db/tables/T"
    assert ml_t["kind"] == "table"
    assert ml_o["id"] == "widgets/db/plsql/P"
    assert ml_o["kind"] == "procedure"
    assert ml_o["description"] == "does a thing"


def test_no_vendor_name_survives_in_the_default_product():
    """The default must stay neutral.

    Card ids and the product facet were hardcoded to one vendor's product name, which meant
    a schema parsed for anything else produced cards filed under the wrong product. A
    vendor-shaped default would quietly reintroduce that.
    """
    from hivedbparse.emit import DEFAULT_PRODUCT

    assert DEFAULT_PRODUCT == "db"
    t = Table("T", "MOD", columns=[Column("A")], dialects={"oracle"})
    assert card_id(t) == "db/db/tables/T"
    assert card_id(t, "widgets") == "widgets/db/tables/T"


def test_product_reaches_every_rendered_reference():
    """Not just the id: the facet, the foreign-key links and the trigger links all carry it,
    and a card whose links point at another product's ids resolves to nothing."""
    t = Table(
        "ORDERS", "MOD",
        columns=[Column("CUST_ID", type_oracle="NUMBER")],
        fks=[("CUST_ID", "CUSTOMER", "ID")],
        triggers=["ORDERS_AI"],
        dialects={"oracle"},
    )
    md = table_card(t, "widgets")
    assert "widgets/db/tables/CUSTOMER" in md
    assert "widgets/db/plsql/ORDERS_AI" in md
    assert _frontmatter_dict(md)["product"] == "widgets"
    assert "wms/" not in md

from okfdbparse.model import Column, Table
from okfdbparse.parse_aux import apply_aux


def _t():
    return {
        "MASTER_STAGING_DATA": Table(
            name="MASTER_STAGING_DATA",
            module="DOM",
            columns=[Column("EVENT_ID"), Column("EVENT_TYPE")],
        )
    }


def test_table_and_column_comments_attached_verbatim():
    tabs = _t()
    apply_aux(
        tabs,
        (
            "comment on table MASTER_STAGING_DATA is 'Table to stage inbound events';\n"
            'COMMENT ON COLUMN "MASTER_STAGING_DATA"."EVENT_ID" '
            "IS 'Unique identifier of the event';"
        ),
        "oracle",
    )
    t = tabs["MASTER_STAGING_DATA"]
    assert t.comment == "Table to stage inbound events"
    assert {c.name: c.comment for c in t.columns}["EVENT_ID"] == "Unique identifier of the event"


def test_foreign_key_and_index_attached():
    tabs = _t()
    apply_aux(
        tabs,
        (
            'ALTER TABLE "MASTER_STAGING_DATA" ADD CONSTRAINT FK1 FOREIGN KEY ("EVENT_TYPE") '
            'REFERENCES "SYS_CODE" ("CODE_ID");\n'
            'CREATE UNIQUE INDEX IDX_MSD ON "MASTER_STAGING_DATA" ("EVENT_ID");'
        ),
        "oracle",
    )
    t = tabs["MASTER_STAGING_DATA"]
    assert ("EVENT_TYPE", "SYS_CODE", "CODE_ID") in t.fks
    assert ("IDX_MSD", ["EVENT_ID"], True) in t.indexes


def test_multi_column_foreign_key_and_non_unique_index():
    tabs = _t()
    apply_aux(
        tabs,
        (
            'ALTER TABLE "MASTER_STAGING_DATA" ADD CONSTRAINT FK2 '
            'FOREIGN KEY ("EVENT_ID", "EVENT_TYPE") REFERENCES "SYS_CODE" ("ID", "CODE");\n'
            'CREATE INDEX IDX_MULTI ON "MASTER_STAGING_DATA" ("EVENT_ID", "EVENT_TYPE");'
        ),
        "oracle",
    )
    t = tabs["MASTER_STAGING_DATA"]
    assert ("EVENT_ID", "SYS_CODE", "ID") in t.fks
    assert ("EVENT_TYPE", "SYS_CODE", "CODE") in t.fks
    assert ("IDX_MULTI", ["EVENT_ID", "EVENT_TYPE"], False) in t.indexes


def test_sequence_attached_to_owning_table_by_name_prefix():
    tabs = _t()
    apply_aux(tabs, "CREATE SEQUENCE MASTER_STAGING_DATA_SEQ START WITH 1;", "oracle")
    assert "MASTER_STAGING_DATA_SEQ" in tabs["MASTER_STAGING_DATA"].sequences


def test_orphan_sequence_is_not_attached_and_does_not_crash():
    tabs = _t()
    apply_aux(tabs, "CREATE SEQUENCE COMPLETELY_UNRELATED_SEQ START WITH 1;", "oracle")
    assert tabs["MASTER_STAGING_DATA"].sequences == []


def test_comment_fk_index_referencing_unknown_table_is_skipped_not_crashed():
    tabs = _t()
    apply_aux(
        tabs,
        (
            "COMMENT ON TABLE NO_SUCH_TABLE IS 'orphan comment';\n"
            'ALTER TABLE "NO_SUCH_TABLE" ADD CONSTRAINT FK9 FOREIGN KEY ("X") '
            'REFERENCES "Y" ("Z");\n'
            'CREATE INDEX IDX_ORPHAN ON "NO_SUCH_TABLE" ("X");\n'
            "COMMENT ON TABLE MASTER_STAGING_DATA IS 'still works';"
        ),
        "oracle",
    )
    t = tabs["MASTER_STAGING_DATA"]
    assert t.comment == "still works"
    assert t.fks == []
    assert t.indexes == []


def test_db2_dialect_is_mapped_and_does_not_raise():
    tabs = _t()
    apply_aux(
        tabs,
        (
            "COMMENT ON TABLE MASTER_STAGING_DATA IS 'db2 comment';\n"
            "ALTER TABLE MASTER_STAGING_DATA ADD CONSTRAINT FK1 FOREIGN KEY (EVENT_TYPE) "
            "REFERENCES SYS_CODE (CODE_ID);\n"
            "CREATE UNIQUE INDEX IDX_MSD ON MASTER_STAGING_DATA (EVENT_ID);"
        ),
        "db2",
    )
    t = tabs["MASTER_STAGING_DATA"]
    assert t.comment == "db2 comment"
    assert ("EVENT_TYPE", "SYS_CODE", "CODE_ID") in t.fks
    assert ("IDX_MSD", ["EVENT_ID"], True) in t.indexes


def test_unparseable_statement_is_skipped_not_crashed():
    tabs = _t()
    apply_aux(
        tabs,
        (
            "COMMENT ON TABLE MASTER_STAGING_DATA IS 'before garbage';\n"
            "THIS IS NOT VALID SQL AT ALL (((;\n"
            "COMMENT ON TABLE MASTER_STAGING_DATA IS 'after garbage';"
        ),
        "oracle",
    )
    assert tabs["MASTER_STAGING_DATA"].comment == "after garbage"

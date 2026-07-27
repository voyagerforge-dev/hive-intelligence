from hivedbparse.model import Column, Table
from hivedbparse.parse_aux import apply_aux, attach_sequences


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
    attach_sequences(tabs, "CREATE SEQUENCE MASTER_STAGING_DATA_SEQ START WITH 1;")
    assert "MASTER_STAGING_DATA_SEQ" in tabs["MASTER_STAGING_DATA"].sequences


def test_orphan_sequence_is_not_attached_and_does_not_crash():
    tabs = _t()
    attach_sequences(tabs, "CREATE SEQUENCE COMPLETELY_UNRELATED_SEQ START WITH 1;")
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


def test_apply_aux_skips_non_aux_statements_without_warning(caplog):
    import logging
    tabs = _t()
    # a PL/SQL body (with an internal `/` division) + an INSERT must be skipped
    # WITHOUT a parse attempt/warning; the COMMENT still attaches.
    sql = (
        "BEGIN\n  UPDATE X SET A = A / B WHERE ID = 1;\nEND;\n/\n"
        "INSERT INTO MASTER_STAGING_DATA (EVENT_ID) VALUES (1);\n"
        "comment on table MASTER_STAGING_DATA is 'kept';\n"
    )
    with caplog.at_level(logging.WARNING, logger="hivedbparse.parse_aux"):
        apply_aux(tabs, sql, "oracle")
    assert tabs["MASTER_STAGING_DATA"].comment == "kept"
    assert not any("could not parse aux" in r.getMessage() for r in caplog.records)


def test_create_index_with_storage_tail_is_attached():
    # Real Oracle DDL trails CREATE INDEX with storage clauses; sqlglot degrades
    # the whole statement to Command, which used to silently drop the index
    # (~12k index statements in the corpus -> only 77 tables had any).
    tabs = _t()
    apply_aux(
        tabs,
        "CREATE INDEX IDX_MSD_EVENT ON MASTER_STAGING_DATA (EVENT_ID) "
        "TABLESPACE TS_IDX PCTFREE 10 INITRANS 2 MAXTRANS 255;",
        "oracle",
    )
    assert [(n, c) for n, c, _u in tabs["MASTER_STAGING_DATA"].indexes] == [
        ("IDX_MSD_EVENT", ["EVENT_ID"])
    ]


def test_unknown_target_warns_on_the_soft_logger_not_the_gate(caplog):
    import logging
    tabs = _t()
    with caplog.at_level(logging.WARNING):
        apply_aux(tabs, "comment on table NOT_CARDED is 'x';", "oracle")
    names = {r.name for r in caplog.records}
    assert "hivedbparse.aux_unattached" in names      # reported
    assert "hivedbparse.parse_aux" not in names       # NOT gated


def test_alter_table_foreign_key_with_trailing_state_is_attached():
    tabs = _t()
    tabs["OTHER"] = Table(name="OTHER", module="DOM", columns=[Column("OID")])
    apply_aux(
        tabs,
        "ALTER TABLE MASTER_STAGING_DATA ADD CONSTRAINT FK1 FOREIGN KEY (EVENT_ID) "
        "REFERENCES OTHER (OID) ENABLE NOVALIDATE;",
        "oracle",
    )
    assert ("EVENT_ID", "OTHER", "OID") in tabs["MASTER_STAGING_DATA"].fks


def test_schema_qualified_index_name_is_attached():
    tabs = _t()
    apply_aux(
        tabs,
        "CREATE UNIQUE INDEX session.msd_idx1 ON session.MASTER_STAGING_DATA(EVENT_ID) "
        "TABLESPACE TS PCTFREE 10;",
        "oracle",
    )
    assert [(n, c) for n, c, _u in tabs["MASTER_STAGING_DATA"].indexes] == [
        ("msd_idx1", ["EVENT_ID"])
    ]


def test_db2_alter_foreign_key_enforcement_is_not_gated(caplog):
    import logging
    # DB2 `ALTER TABLE t ALTER FOREIGN KEY fk NOT ENFORCED` toggles enforcement;
    # it carries no FK definition, so it is neither attached nor a gate failure.
    tabs = _t()
    with caplog.at_level(logging.WARNING):
        apply_aux(
            tabs,
            "ALTER TABLE MASTER_STAGING_DATA ALTER FOREIGN KEY FK_X NOT ENFORCED;",
            "db2",
        )
    assert not any(r.name == "hivedbparse.parse_aux" for r in caplog.records)


def test_sequence_exact_name_match_beats_a_longer_sibling_table():
    # Flag 2: `_sequence_owner` used longest-match, so an exact-name owner lost
    # to any longer table that merely starts with the stem -- ROUTE_SEQ landed
    # on ROUTE_PLAN_LEG_SET instead of ROUTE. Exact match must win outright.
    from hivedbparse.model import Column, Table
    tabs = {
        "ROUTE": Table(name="ROUTE", module="X", columns=[Column("ROUTE_ID")]),
        "ROUTE_PLAN_LEG_SET": Table(
            name="ROUTE_PLAN_LEG_SET", module="X", columns=[Column("ID")]
        ),
    }
    attach_sequences(tabs, "CREATE SEQUENCE ROUTE_SEQ START WITH 1;")
    assert tabs["ROUTE"].sequences == ["ROUTE_SEQ"]
    assert tabs["ROUTE_PLAN_LEG_SET"].sequences == []


def test_sequence_exact_match_is_case_insensitive():
    from hivedbparse.model import Column, Table
    tabs = {
        "job_hist": Table(name="job_hist", module="X", columns=[Column("ID")]),
        "JOB_HIST_ARCHIVE": Table(name="JOB_HIST_ARCHIVE", module="X", columns=[Column("ID")]),
    }
    attach_sequences(tabs, "CREATE SEQUENCE JOB_HIST_SEQ START WITH 1;")
    assert tabs["job_hist"].sequences == ["JOB_HIST_SEQ"]


def test_sequence_prefix_fallback_still_works_without_exact_match():
    # No exact table for the stem -> longest table that is a prefix of the stem.
    from hivedbparse.model import Column, Table
    tabs = {"ORDER_LINE": Table(name="ORDER_LINE", module="X", columns=[Column("ID")])}
    attach_sequences(tabs, "CREATE SEQUENCE ORDER_LINE_STATUS_SEQ START WITH 1;")
    assert tabs["ORDER_LINE"].sequences == ["ORDER_LINE_STATUS_SEQ"]


def test_db2_create_or_replace_sequence_attaches_by_name():
    # DB2 spells sequences `CREATE OR REPLACE SEQUENCE x ... NO ORDER!` -- these
    # degrade to Command in sqlglot, so they're attached by name extraction, not
    # by parsing. ACCESSORIAL_ID_SEQ -> ACCESSORIAL (via the prefix fallback).
    from hivedbparse.model import Column, Table
    tabs = {"ACCESSORIAL": Table(name="ACCESSORIAL", module="X", columns=[Column("ID")])}
    attach_sequences(
        tabs,
        "create or replace sequence ACCESSORIAL_ID_SEQ start with 23 no order!")
    assert "ACCESSORIAL_ID_SEQ" in tabs["ACCESSORIAL"].sequences


def test_db2_bang_sequence_file_blob_attaches_all():
    from hivedbparse.model import Column, Table
    tabs = {
        "ACTION_TYPE": Table(name="ACTION_TYPE", module="X", columns=[Column("ID")]),
        "AI_MASTER": Table(name="AI_MASTER", module="X", columns=[Column("ID")]),
    }
    blob = ("create or replace sequence ACTION_TYPE_ID_SEQ start with 3 no order!\n"
            "create or replace sequence AI_MASTER_ID_SEQ start with 3 no order!\n")
    attach_sequences(tabs, blob)
    assert "ACTION_TYPE_ID_SEQ" in tabs["ACTION_TYPE"].sequences
    assert "AI_MASTER_ID_SEQ" in tabs["AI_MASTER"].sequences

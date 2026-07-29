import pytest

from hiveserve import ledger


def _conn(tmp_path):
    return ledger.connect(tmp_path / "obj.db")


def test_objective_lifecycle(tmp_path):
    c = _conn(tmp_path)
    o = ledger.start_objective(c, owner="alice", mode="investigate", goal="slow waves")
    assert o["mode"] == "investigate" and o["status"] == "open" and o["owner"] == "alice"
    oid = o["id"]
    ledger.append_entry(c, owner="alice", objective_id=oid, kind="finding",
                        content="replen lagging", card_ids=["wave-replen"])
    ledger.record_quiz_result(c, owner="alice", objective_id=oid, concept_id="wave-replen", score=0.8)
    done = ledger.set_status(c, owner="alice", objective_id=oid, status="resolved")
    assert done["status"] == "resolved"
    full = ledger.get_objective(c, owner="alice", objective_id=oid)
    kinds = [e["kind"] for e in full["entries"]]
    assert kinds == ["finding", "quiz_result"]
    assert full["entries"][0]["card_ids"] == ["wave-replen"]


def test_owner_scoping(tmp_path):
    c = _conn(tmp_path)
    o = ledger.start_objective(c, owner="alice", mode="learn", goal="x")
    assert ledger.get_objective(c, owner="bob", objective_id=o["id"]) is None
    assert ledger.append_entry(c, owner="bob", objective_id=o["id"], kind="note", content="x") is None
    assert ledger.set_status(c, owner="bob", objective_id=o["id"], status="done") is None
    assert ledger.record_quiz_result(c, owner="bob", objective_id=o["id"], concept_id="x", score=1.0) is None
    assert ledger.list_objectives(c, owner="bob") == []
    assert len(ledger.list_objectives(c, owner="alice")) == 1


def test_validation(tmp_path):
    c = _conn(tmp_path)
    with pytest.raises(ValueError):
        ledger.start_objective(c, owner="a", mode="bogus", goal="x")
    o = ledger.start_objective(c, owner="a", mode="implement", goal="x")
    with pytest.raises(ValueError):
        ledger.append_entry(c, owner="a", objective_id=o["id"], kind="bogus", content="x")
    with pytest.raises(ValueError):
        ledger.set_status(c, owner="a", objective_id=o["id"], status="bogus")


def test_external_ref_roundtrip(tmp_path):
    c = _conn(tmp_path)
    ref = {"provider": "zendesk", "id": "123", "url": "http://z/123"}
    o = ledger.start_objective(c, owner="a", mode="investigate", goal="x", external_ref=ref)
    assert ledger.get_objective(c, owner="a", objective_id=o["id"])["external_ref"] == ref


def test_memory_remember_roundtrip(tmp_path):
    c = _conn(tmp_path)
    m = ledger.remember(c, owner="alice", text="Alpha pick-confirm needs a second scan",
                        tags=["alpha", "pick-confirm"], card_ids=["widgets/pick-confirm"],
                        external_ref={"provider": "zendesk", "id": "1421"}, client="alpha")
    assert m["owner"] == "alice" and m["client"] == "alpha"
    assert m["text"] == "Alpha pick-confirm needs a second scan"
    assert m["tags"] == ["alpha", "pick-confirm"]
    assert m["card_ids"] == ["widgets/pick-confirm"]
    assert m["external_ref"] == {"provider": "zendesk", "id": "1421"}
    assert m["visibility"] == "private"
    got = ledger.get_memory(c, owner="alice", memory_id=m["id"])
    assert got == m


def test_memory_defaults_minimal(tmp_path):
    c = _conn(tmp_path)
    m = ledger.remember(c, owner="alice", text="a bare note")
    assert m["tags"] == [] and m["card_ids"] == [] and m["external_ref"] is None
    assert m["client"] is None and m["visibility"] == "private"


def test_memory_recall_filters(tmp_path):
    c = _conn(tmp_path)
    ledger.remember(c, owner="alice", text="Alpha wave replen is nightly",
                    tags=["alpha", "replen"], card_ids=["widgets/replenishment"], client="alpha")
    ledger.remember(c, owner="alice", text="ACME sprockets uses zones",
                    tags=["acme", "sprockets"], card_ids=["sprockets/zones"], client="acme")
    ledger.remember(c, owner="alice", text="generic ops note", tags=["ops"])

    assert {m["text"] for m in ledger.recall(c, owner="alice")} == {
        "Alpha wave replen is nightly", "ACME sprockets uses zones", "generic ops note"}
    assert [m["text"] for m in ledger.recall(c, owner="alice", query="replen")] == \
        ["Alpha wave replen is nightly"]
    assert [m["text"] for m in ledger.recall(c, owner="alice", query="alpha")] == \
        ["Alpha wave replen is nightly"]  # matches a tag
    assert [m["text"] for m in ledger.recall(c, owner="alice", client="acme")] == \
        ["ACME sprockets uses zones"]
    assert [m["text"] for m in ledger.recall(c, owner="alice", card_id="widgets/replenishment")] == \
        ["Alpha wave replen is nightly"]
    assert [m["text"] for m in ledger.recall(c, owner="alice", tags=["alpha", "replen"])] == \
        ["Alpha wave replen is nightly"]
    assert ledger.recall(c, owner="alice", tags=["alpha", "missing"]) == []
    assert len(ledger.recall(c, owner="alice", limit=1)) == 1


def test_memory_recall_owner_scoped(tmp_path):
    c = _conn(tmp_path)
    ledger.remember(c, owner="alice", text="alice only")
    assert ledger.recall(c, owner="bob") == []


def test_memory_recall_tag_branch_isolated(tmp_path):
    c = _conn(tmp_path)
    ledger.remember(c, owner="alice", text="nightly batch window is 2am", tags=["cutoff"])
    ledger.remember(c, owner="alice", text="unrelated note", tags=["misc"])
    # 'cutoff' is only a tag, never a substring of any text -> only the tag branch can match it
    assert [m["text"] for m in ledger.recall(c, owner="alice", query="cutoff")] == \
        ["nightly batch window is 2am"]


def test_memory_recall_and_combination_and_subset(tmp_path):
    c = _conn(tmp_path)
    ledger.remember(c, owner="alice", text="Alpha wave replen is nightly",
                    tags=["replen", "wave"], client="alpha")
    ledger.remember(c, owner="alice", text="ACME sprockets uses zones",
                    tags=["sprockets"], client="acme")
    # AND: client matches the alpha row but query does not -> empty
    assert ledger.recall(c, owner="alice", client="alpha", query="acme") == []
    # AND: both filters match the same row
    assert [m["text"] for m in ledger.recall(c, owner="alice", client="alpha", query="replen")] == \
        ["Alpha wave replen is nightly"]
    # subset: requesting a proper subset of a row's tags still matches
    assert [m["text"] for m in ledger.recall(c, owner="alice", tags=["replen"])] == \
        ["Alpha wave replen is nightly"]


def test_memory_recall_orders_newest_first(tmp_path):
    c = _conn(tmp_path)
    ledger.remember(c, owner="alice", text="first")
    ledger.remember(c, owner="alice", text="second")
    ledger.remember(c, owner="alice", text="third")
    assert [m["text"] for m in ledger.recall(c, owner="alice")] == ["third", "second", "first"]


def test_memory_forget_owner_scoped(tmp_path):
    c = _conn(tmp_path)
    m = ledger.remember(c, owner="alice", text="x")
    assert ledger.forget(c, owner="bob", memory_id=m["id"]) is False
    assert ledger.get_memory(c, owner="alice", memory_id=m["id"]) is not None
    assert ledger.forget(c, owner="alice", memory_id=m["id"]) is True
    assert ledger.get_memory(c, owner="alice", memory_id=m["id"]) is None


def test_memory_visibility_flip(tmp_path):
    c = _conn(tmp_path)
    m = ledger.remember(c, owner="alice", text="x", client="alpha")
    updated = ledger.set_memory_visibility(c, owner="alice", memory_id=m["id"],
                                           visibility="promotion_requested")
    assert updated["visibility"] == "promotion_requested"
    assert ledger.set_memory_visibility(c, owner="bob", memory_id=m["id"],
                                        visibility="private") is None
    with pytest.raises(ValueError):
        ledger.set_memory_visibility(c, owner="alice", memory_id=m["id"], visibility="bogus")


def test_promotion_record_shape(tmp_path):
    c = _conn(tmp_path)
    m = ledger.remember(c, owner="alice", text="Alpha mod: second scan on pick-confirm",
                        tags=["alpha", "pick-confirm"], card_ids=["widgets/pick-confirm"],
                        external_ref={"provider": "zendesk", "id": "1421"}, client="alpha")
    rec = ledger.promotion_record(m, owner="alice")
    assert rec == {
        "client": "alpha", "product": "", "title": "",
        "memory": "Alpha mod: second scan on pick-confirm", "context": "",
        "platform": "", "related": ["widgets/pick-confirm"], "tags": ["alpha", "pick-confirm"],
        "citations": [], "supersedes": [],
        "external_ref": {"provider": "zendesk", "id": "1421"},
        "submitted_by": "alice", "status": "approved",
    }


def test_promote_memory_guards(tmp_path):
    c = _conn(tmp_path)
    assert ledger.promote_memory(c, owner="alice", memory_id="nope") == {"error": "not_found"}
    m0 = ledger.remember(c, owner="alice", text="no client note")
    assert ledger.promote_memory(c, owner="alice", memory_id=m0["id"]) == {"error": "client_required"}
    assert ledger.get_memory(c, owner="alice", memory_id=m0["id"])["visibility"] == "private"
    m1 = ledger.remember(c, owner="alice", text="alpha note", tags=["alpha"],
                         card_ids=["widgets/pick-confirm"], client="alpha")
    out = ledger.promote_memory(c, owner="alice", memory_id=m1["id"])
    assert out["memory_id"] == m1["id"]
    assert out["record"]["client"] == "alpha" and out["record"]["submitted_by"] == "alice"
    assert ledger.get_memory(c, owner="alice",
                            memory_id=m1["id"])["visibility"] == "promotion_requested"


def test_promote_memory_owner_scoped(tmp_path):
    c = _conn(tmp_path)
    m = ledger.remember(c, owner="alice", text="alpha", client="alpha")
    assert ledger.promote_memory(c, owner="bob", memory_id=m["id"]) == {"error": "not_found"}

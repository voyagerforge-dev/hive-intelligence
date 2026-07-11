import pytest
from okfserve import ledger


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
    m = ledger.remember(c, owner="alice", text="ALPHA pick-confirm needs a second scan",
                        tags=["alpha", "pick-confirm"], card_ids=["wms/pick-confirm"],
                        external_ref={"provider": "zendesk", "id": "1421"}, client="alpha")
    assert m["owner"] == "alice" and m["client"] == "alpha"
    assert m["text"] == "ALPHA pick-confirm needs a second scan"
    assert m["tags"] == ["alpha", "pick-confirm"]
    assert m["card_ids"] == ["wms/pick-confirm"]
    assert m["external_ref"] == {"provider": "zendesk", "id": "1421"}
    assert m["visibility"] == "private"
    got = ledger.get_memory(c, owner="alice", memory_id=m["id"])
    assert got == m


def test_memory_defaults_minimal(tmp_path):
    c = _conn(tmp_path)
    m = ledger.remember(c, owner="alice", text="a bare note")
    assert m["tags"] == [] and m["card_ids"] == [] and m["external_ref"] is None
    assert m["client"] is None and m["visibility"] == "private"

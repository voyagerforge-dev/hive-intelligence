from pathlib import Path

from okfserve.eval import load_qa
from okfserve.resolver import load_index

ROOT = Path(__file__).resolve().parents[3]


def test_dataset_ids_exist_in_bundle():
    qa = load_qa(Path(__file__).resolve().parents[1] / "data" / "wave_replen_qa.jsonl")
    known = {c["id"] for c in load_index(ROOT / "concepts")}
    assert len(qa) >= 14
    missing = {cid for row in qa for cid in row["expected_card_ids"] if cid not in known}
    assert not missing, f"expected_card_ids not in concepts/: {missing}"


def test_memory_qa_wellformed():
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "data" / "memory_qa.jsonl"
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    assert rows, "memory_qa.jsonl must be non-empty"
    for r in rows:
        assert "id" in r and "question" in r and "expected_card_ids" in r
    # at least one in-scope alpha hit, one isolation (no client), one cross-client case
    assert any(r.get("client") == "alpha" and r.get("expects_memory") for r in rows)
    assert any(r.get("client") in (None, "") for r in rows)
    assert any(r.get("client") == "acme" for r in rows)

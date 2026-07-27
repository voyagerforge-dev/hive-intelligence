"""Dataset integrity.

Two layers, deliberately:

* **Fixture layer** (always runs). Validates the eval machinery against the
  synthetic corpus in ``tests/fixtures/corpus``. Carries no real-world domain
  vocabulary, so it survives the corpus being split into its own repository.
* **Live-corpus layer** (skips when absent). Validates the domain-specific QA
  datasets in ``data/`` against the real bundle. Those datasets reference real
  card ids, so they are corpus-side and move with it. When they do, these tests
  skip rather than fail.
"""

import json
from pathlib import Path

import pytest

from hiveserve.eval import load_qa
from hiveserve.resolver import load_index

ROOT = Path(__file__).resolve().parents[3]
TESTS = Path(__file__).resolve().parent
DATA = TESTS.parent / "data"

FIXTURE_CORPUS = TESTS / "fixtures" / "corpus"
FIXTURE_CONCEPTS = FIXTURE_CORPUS / "concepts"
FIXTURE_CLIENTS = FIXTURE_CORPUS / "clients"
FIXTURE_QA = TESTS / "fixtures" / "qa" / "fixture_qa.jsonl"

LIVE_CONCEPTS = ROOT / "concepts"
LIVE_CLIENTS = ROOT / "clients"

needs_live_corpus = pytest.mark.skipif(
    not LIVE_CONCEPTS.is_dir(),
    reason="live corpus not present (it lives in its own repository)",
)

# The QA sets under data/ name real cards and real clients, so they are corpus-side
# and travel with the corpus. They can be absent while the corpus is present, and
# vice versa, so the two guards are separate and stack where a test needs both.
needs_live_qa = pytest.mark.skipif(
    not DATA.is_dir(),
    reason="live QA datasets not present (they live with the corpus)",
)


def _rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


# --------------------------------------------------------------------------
# Fixture layer. Always runs.
# --------------------------------------------------------------------------


def test_fixture_corpus_covers_every_card_type():
    """The fixture exists to prove the machinery is domain-neutral. If it stops
    covering a card type, it stops proving that."""
    idx = load_index(FIXTURE_CONCEPTS, FIXTURE_CLIENTS)
    types = {c.get("type") for c in idx}
    assert types == {"concept", "memory", "correction", "issue", "dbobject"}, types


def test_fixture_corpus_has_two_isolated_clients():
    idx = load_index(FIXTURE_CONCEPTS, FIXTURE_CLIENTS)
    clients = {c.get("client") for c in idx if c.get("client")}
    assert len(clients) >= 2, f"need >=2 clients to test isolation, got {clients}"


def test_fixture_corpus_wires_a_correction_to_its_target():
    from hiveserve.resolver import corrections_by_target

    idx = load_index(FIXTURE_CONCEPTS, FIXTURE_CLIENTS)
    cbt = corrections_by_target(idx)
    assert cbt, "fixture must exercise the corrections override path"
    for target, corrections in cbt.items():
        assert target in {c["id"] for c in idx}, f"correction targets unknown card {target}"
        assert corrections


def test_fixture_qa_ids_resolve():
    idx = {c["id"] for c in load_index(FIXTURE_CONCEPTS, FIXTURE_CLIENTS)}
    rows = _rows(FIXTURE_QA)
    assert rows, "fixture_qa.jsonl must be non-empty"
    for r in rows:
        assert "id" in r and "question" in r and "expected_card_ids" in r
        for cid in r["expected_card_ids"]:
            assert cid in idx, f"{r['id']}: {cid} missing from fixture corpus"
        if r.get("expects_memory"):
            assert r["expects_memory"] in idx, f"{r['id']}: memory card missing"


def test_fixture_qa_covers_scope_cases():
    """In-scope memory hit, no-client case, and a second client."""
    rows = _rows(FIXTURE_QA)
    assert any(r.get("client") and r.get("expects_memory") for r in rows)
    assert any(r.get("client") in (None, "") for r in rows)
    assert len({r.get("client") for r in rows if r.get("client")}) >= 2


# --------------------------------------------------------------------------
# Live-corpus layer. Skips once the corpus moves to its own repository.
# --------------------------------------------------------------------------


@needs_live_corpus
@needs_live_qa
def test_dataset_ids_exist_in_bundle():
    qa = load_qa(DATA / "wave_replen_qa.jsonl")
    known = {c["id"] for c in load_index(LIVE_CONCEPTS)}
    assert len(qa) >= 14
    missing = {cid for row in qa for cid in row["expected_card_ids"] if cid not in known}
    assert not missing, f"expected_card_ids not in concepts/: {missing}"


@needs_live_qa
def test_memory_qa_wellformed():
    rows = _rows(DATA / "memory_qa.jsonl")
    assert rows, "memory_qa.jsonl must be non-empty"
    for r in rows:
        assert "id" in r and "question" in r and "expected_card_ids" in r
    # at least one in-scope hit, one isolation case, one cross-client case
    assert any(r.get("client") == "alpha" and r.get("expects_memory") for r in rows)
    assert any(r.get("client") in (None, "") for r in rows)
    assert any(r.get("client") == "acme" for r in rows)


@needs_live_corpus
@needs_live_qa
def test_memory_qa_ids_resolve():
    idx = {c["id"] for c in load_index(LIVE_CONCEPTS, LIVE_CLIENTS)}
    for r in _rows(DATA / "memory_qa.jsonl"):
        for cid in r["expected_card_ids"]:
            assert cid in idx, f"{r['id']}: {cid} missing from corpus"
        if r.get("expects_memory"):
            assert r["expects_memory"] in idx

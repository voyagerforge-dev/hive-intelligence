from hivegen.memory import memory_to_record, record_to_memory

REC = {
    "client": "alpha", "product": "wms", "title": "ALPHA second scan",
    "description": "alpha mod", "memory": "ALPHA requires a second scan.",
    "context": "Applies to ALPHA only.", "platform": "wmos",
    "related": ["wms/allocation-process"], "tags": ["alpha", "allocation"],
    "citations": ["alpha-enh.md"], "supersedes": [], "submitted_by": "u@x.dev",
    "status": "approved", "timestamp": "2026-07-12",
    "resource": "https://hive.example.com/card/clients/alpha/memory/alpha-second-scan",
}


def test_record_to_memory_frontmatter_and_body():
    card = record_to_memory(REC)
    assert card.startswith("---\n")
    assert "type: memory" in card
    assert "client: alpha" in card and "product: wms" in card
    assert "## Memory\n\nALPHA requires a second scan." in card
    assert "## Context\n\nApplies to ALPHA only." in card
    assert "kind: memory-source" in card and "ref: alpha-enh.md" in card


def test_round_trips_losslessly():
    rec = memory_to_record(record_to_memory(REC))
    for k in ("client", "product", "title", "memory", "context", "platform",
              "related", "tags", "supersedes", "submitted_by", "status"):
        assert rec[k] == REC[k], k
    assert rec["citations"] == ["alpha-enh.md"]


def test_memory_to_record_tolerates_missing_body():
    rec = memory_to_record("---\ntype: memory\nclient: alpha\nproduct: wms\ntitle: T\n---\n")
    assert rec["client"] == "alpha" and rec["memory"] == "" and rec["context"] == ""

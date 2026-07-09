import re

from okfgen.corrections import record_to_correction, correction_to_record

REC = {
    "corrects": "slotting/data-requirements",
    "title": "Duplicate slot numbers are not allowed",
    "description": "Corrects the inverted duplicate-slot rule.",
    "correction": "Duplicate slot numbers are **not** allowed.",
    "rationale": "Source: Data Requirements Guide, Slots Import section.",
    "citations": ["slotting-slotting-optimization-2020-data-requirements-guide.md"],
    "supersedes": [],
    "product": "slotting",
    "status": "approved",
    "timestamp": "2026-07-09",
}


def test_record_to_correction_frontmatter_and_body():
    md = record_to_correction(REC)
    assert md.startswith("---\n")
    assert "type: correction" in md
    assert "corrects: slotting/data-requirements" in md
    assert "product: slotting" in md
    assert "status: approved" in md
    assert "- kind: correction-source" in md and "ref: slotting-slotting-optimization-2020-data-requirements-guide.md" in md
    assert "## Correction\n\nDuplicate slot numbers are **not** allowed." in md
    assert "## Rationale\n\nSource: Data Requirements Guide" in md
    # resource is an EMPTY placeholder for conformance_pass to fill; # Citations added by conformance_pass
    assert re.search(r"(?m)^resource: *(''|\"\"|)$", md)
    assert "# Citations" not in md


def test_round_trip():
    md = record_to_correction(REC)
    back = correction_to_record(md)
    for k in ("corrects", "title", "description", "correction", "rationale",
              "citations", "supersedes", "product", "status", "timestamp"):
        assert back[k] == REC[k], k


def test_round_trip_with_dashes_in_fields():
    rec = dict(REC, title="Before --- after: duplicate rule", description="Fixes the --- inverted --- rule.")
    back = correction_to_record(record_to_correction(rec))
    for k in ("corrects", "title", "description", "correction", "rationale",
              "citations", "supersedes", "product", "status", "timestamp"):
        assert back[k] == rec[k], k

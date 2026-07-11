import importlib.util
from pathlib import Path

import pytest

from okfauthor.submissions import (
    build_correction_submission,
    build_memory_submission,
)

_TOOLING = Path(__file__).resolve().parents[2]   # knowledge/okf/tooling


def _load(script):
    spec = importlib.util.spec_from_file_location(
        script, _TOOLING / "okf-gen" / "scripts" / f"{script}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_memory_submission_roundtrips_through_parser():
    sub = build_memory_submission(owner="u@x.dev", client="alpha", product="wms",
        title="Second scan", lesson="ALPHA requires a second scan.",
        context="ALPHA only.", platform="wmos", related=["wms/allocation-process"],
        citations=["alpha.md"])
    assert sub["labels"] == ["okf-memory"]
    assert sub["title"] == "[memory] Second scan"
    rec = _load("memory_from_issue").parse_issue(sub["body"])
    assert rec["client"] == "alpha" and rec["product"] == "wms"
    assert rec["memory"] == "ALPHA requires a second scan."
    assert rec["related"] == ["wms/allocation-process"]
    assert rec["citations"] == ["alpha.md"]


def test_correction_submission_roundtrips_through_parser():
    sub = build_correction_submission(owner="u@x.dev", target_concept_id="slotting/data-requirements",
        corrected_fact="Duplicate slots are not allowed.", rationale="Per the guide.",
        citations=["slotting.md"])
    assert sub["labels"] == ["okf-correction"]
    rec = _load("correction_from_issue").parse_issue(sub["body"])
    assert rec["corrects"] == "slotting/data-requirements"
    assert rec["correction"] == "Duplicate slots are not allowed."
    assert rec["citations"] == ["slotting.md"]


def test_memory_submission_requires_client():
    with pytest.raises(ValueError):
        build_memory_submission(owner="u@x.dev", client="", product="wms",
                                title="t", lesson="l")


def test_submitted_by_appears_in_body():
    sub = build_memory_submission(owner="u@x.dev", client="alpha", product="wms",
                                  title="t", lesson="l")
    assert "u@x.dev" in sub["body"]

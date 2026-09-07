import pytest

# The parsers come from the pinned distribution, not from a sibling checkout. This used to
# load them out of `../hive-gen/scripts/` by path, which only ever worked because the two
# packages happen to sit in one tree; hive-gen publishes them from 0.7.0, so the dependency
# this package already declares is what supplies them.
from hivegen.scripts.correction_from_issue import parse_issue as parse_correction_issue
from hivegen.scripts.memory_from_issue import parse_issue as parse_memory_issue

from hiveauthor.submissions import (
    build_correction_submission,
    build_memory_submission,
)


def test_memory_submission_roundtrips_through_parser():
    sub = build_memory_submission(owner="u@x.dev", client="alpha", product="widgets",
        title="Second scan", lesson="Alpha requires a second scan.",
        context="Alpha only.", platform="bench", related=["widgets/allocation-process"],
        citations=["alpha.md"])
    assert sub["labels"] == ["hive-memory"]
    assert sub["title"] == "[memory] Second scan"
    rec = parse_memory_issue(sub["body"])
    assert rec["client"] == "alpha" and rec["product"] == "widgets"
    assert rec["memory"] == "Alpha requires a second scan."
    assert rec["related"] == ["widgets/allocation-process"]
    assert rec["citations"] == ["alpha.md"]


def test_correction_submission_roundtrips_through_parser():
    sub = build_correction_submission(owner="u@x.dev", target_concept_id="sprockets/data-requirements",
        corrected_fact="Duplicate slots are not allowed.", rationale="Per the guide.",
        citations=["sprockets.md"])
    assert sub["labels"] == ["hive-correction"]
    rec = parse_correction_issue(sub["body"])
    assert rec["corrects"] == "sprockets/data-requirements"
    assert rec["correction"] == "Duplicate slots are not allowed."
    assert rec["citations"] == ["sprockets.md"]


def test_memory_submission_requires_client():
    with pytest.raises(ValueError):
        build_memory_submission(owner="u@x.dev", client="", product="widgets",
                                title="t", lesson="l")


def test_submitted_by_appears_in_body():
    sub = build_memory_submission(owner="u@x.dev", client="alpha", product="widgets",
                                  title="t", lesson="l")
    assert "u@x.dev" in sub["body"]

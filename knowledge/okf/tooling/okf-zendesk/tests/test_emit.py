from okfzendesk.emit import render, write_card
from okfzendesk.model import IssueCard


def _card(**kw):
    base = dict(ticket_id=14872, client="alpha", title="Wave allocation stalls",
                description="d", module="allocation",
                related=["wms/allocation/wave-replen-lag"], tags=["allocation"],
                symptom="s", diagnosis="dg", resolution="r", context="c",
                closed_at="2026-03-14")
    base.update(kw)
    return IssueCard(**base)


def test_render_has_required_frontmatter_and_sections():
    out = render(_card(), version="0.1.0")
    assert "type: issue" in out
    assert "client: alpha" in out
    assert "ref: '14872'" in out
    assert "status: distilled" in out
    assert "## Symptom" in out and "## Diagnosis" in out
    assert "## Resolution" in out and "## Context" in out


def test_write_is_idempotent(tmp_path):
    p1, s1 = write_card(tmp_path, _card(), version="0.1.0")
    p2, s2 = write_card(tmp_path, _card(), version="0.1.0")
    assert p1 == p2
    assert s1 == "written" and s2 == "unchanged"
    assert p1.name == "14872-wave-allocation-stalls.md"
    assert p1.parent.name == "issues" and p1.parent.parent.name == "alpha"


def test_approved_card_is_preserved(tmp_path):
    p, _ = write_card(tmp_path, _card(), version="0.1.0")
    p.write_text(p.read_text().replace("status: distilled", "status: approved")
                 + "\nHuman added this line.\n")
    _, status = write_card(tmp_path, _card(title="Totally different"), version="0.1.0")
    assert status == "preserved"
    assert "Human added this line." in p.read_text()


def test_force_overwrites_approved(tmp_path):
    p, _ = write_card(tmp_path, _card(), version="0.1.0")
    p.write_text(p.read_text().replace("status: distilled", "status: approved"))
    _, status = write_card(tmp_path, _card(), version="0.1.0", force=True)
    assert status == "written"


def test_title_drift_updates_the_same_card_not_a_duplicate(tmp_path):
    """An LLM reworded title must not create a second card for the same ticket."""
    p1, _ = write_card(tmp_path, _card(title="Wave allocation stalls"), version="0.1.0")
    p2, s2 = write_card(tmp_path, _card(title="Allocation halts when replen is behind"),
                        version="0.1.0")
    assert p1 == p2
    assert s2 == "written"
    assert len(list(p1.parent.glob("*.md"))) == 1

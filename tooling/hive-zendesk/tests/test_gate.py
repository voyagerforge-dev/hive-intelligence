from hivezendesk.gate import content_hash, keep
from hivezendesk.model import Comment, Ticket


def _t(**kw):
    base = dict(id=1, subject="Orders not allocating", description="Wave stuck all morning.",
                org_id=1, client="alpha", closed_at="2026-03-14", tags=[],
                comments=[Comment("agent", True, "Replen tasks lagged behind demand; "
                                                 "reran replenishment and the wave allocated.",
                                  "2026-03-14")])
    base.update(kw)
    return Ticket(**base)


def test_keeps_substantive_ticket():
    assert keep(_t(), set()) == (True, "")


def test_drops_thin_content():
    t = _t(description="hi", comments=[])
    ok, reason = keep(t, set())
    assert ok is False and reason == "thin-content"


def test_drops_noise_pattern():
    t = _t(subject="Password reset request", description="Please reset my password for the portal.")
    ok, reason = keep(t, set())
    assert ok is False and reason == "noise-pattern"


def test_drops_no_diagnostic_content():
    # Long enough to clear the thin-content check, so the no-diagnosis rule is what fires.
    t = _t(comments=[Comment("agent", True, "Done.", "2026-03-14")],
           description="The morning wave did not allocate anything for the whole shift today, "
                       "and the team escalated it after the second cutoff was missed again.")
    ok, reason = keep(t, set())
    assert ok is False and reason == "no-diagnosis"


def test_drops_near_duplicate():
    t = _t()
    ok, reason = keep(t, {content_hash(t)})
    assert ok is False and reason == "duplicate"

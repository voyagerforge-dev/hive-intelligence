import pytest

from hivezendesk.emit import render
from hivezendesk.model import IssueCard, RunError, RunReport
from hivezendesk.verify import verify_card, verify_run


def _card(**kw):
    base = dict(ticket_id=1, client="alpha", title="T", description="d", module="allocation",
                related=["wms/a"], tags=[], what_happened="w", how_it_closed="h", closed_at="2026-03-14")
    base.update(kw)
    return IssueCard(**base)


def test_valid_card_passes():
    c = _card()
    verify_card(render(c, "0.1.0"), c, known=set(), card_ids={"wms/a"})


def test_pii_leak_fails():
    c = _card(what_happened="Reported by Jane Doe")
    with pytest.raises(RunError, match="PII"):
        verify_card(render(c, "0.1.0"), c, known={"Jane Doe"}, card_ids={"wms/a"})


def test_email_pattern_in_card_fails():
    c = _card(what_happened="Mail jane.doe@alpha.invalid")
    with pytest.raises(RunError, match="PII"):
        verify_card(render(c, "0.1.0"), c, known=set(), card_ids={"wms/a"})


def test_unresolved_related_fails():
    c = _card(related=["wms/does-not-exist"])
    with pytest.raises(RunError, match="related"):
        verify_card(render(c, "0.1.0"), c, known=set(), card_ids={"wms/a"})


def test_missing_ticket_ref_fails():
    c = _card()
    broken = render(c, "0.1.0").replace("ref: '1'", "ref: ''")
    with pytest.raises(RunError, match="ref"):
        verify_card(broken, c, known=set(), card_ids={"wms/a"})


def test_counts_must_reconcile():
    with pytest.raises(RunError, match="reconcile"):
        verify_run(RunReport(fetched=10, skipped=3, emitted=5, preserved=0))
    verify_run(RunReport(fetched=10, skipped=3, emitted=6, preserved=1))


def test_counts_account_for_cached_pii_held_and_failed():
    verify_run(RunReport(fetched=10, skipped=1, emitted=4, preserved=1,
                         cached=2, pii_held=1, failed=1))
    with pytest.raises(RunError, match="reconcile"):
        verify_run(RunReport(fetched=10, emitted=4, cached=2))


def test_at_cap_slice_fails():
    with pytest.raises(RunError, match="cap"):
        verify_run(RunReport(fetched=1, skipped=0, emitted=1, at_cap_slices=["alpha/42"]))

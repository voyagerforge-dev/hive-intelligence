from okfzendesk.model import Comment, Ticket
from okfzendesk.scrub import known_values, leaks, scrub_text


def test_scrubs_email_and_phone():
    out = scrub_text("Contact jane.doe@alpha.invalid or +1 555 555 0100 please", set())
    assert "jane.doe@alpha.invalid" not in out
    assert "555 1234" not in out
    assert "[email]" in out and "[phone]" in out


def test_scrubs_known_name_in_prose():
    out = scrub_text("Jane Doe confirmed the wave allocated.", {"Jane Doe"})
    assert "Jane Doe" not in out
    assert "[name]" in out


def test_leaks_detects_residual_personal_value():
    assert leaks("Reported by Jane Doe", {"Jane Doe"}) == ["Jane Doe"]
    assert leaks("Reported by [name]", {"Jane Doe"}) == []


def test_known_values_pulls_from_ticket_identity():
    t = Ticket(id=1, subject="s", description="d", org_id=1, client="alpha",
               closed_at="2026-03-14",
               comments=[Comment("agent", True, "b", "2026-03-14")])
    vals = known_values(t, extra_names=["Jane Doe", "", "  "])
    assert "Jane Doe" in vals
    assert "" not in vals


def test_known_values_harvests_emails_from_the_thread():
    t = Ticket(id=1, subject="s", description="mail jane.doe@alpha.invalid", org_id=1,
               client="alpha", closed_at="2026-03-14", comments=[])
    assert "jane.doe@alpha.invalid" in known_values(t)

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


def test_leaks_reports_kinds_never_the_values():
    """The result lands in logs and error messages, so it must not carry the PII."""
    out = leaks("Reported by Jane Doe", {"Jane Doe"})
    assert out == ["known-name"]
    assert "Jane Doe" not in str(out)
    assert leaks("Reported by [name]", {"Jane Doe"}) == []


def test_leaks_detects_sa_id_and_phone_and_email():
    assert leaks("id 0001010000089 here", set()) == ["sa_id"]
    assert leaks("call +1 555 555 0100", set()) == ["phone"]
    assert leaks("mail a@b.co", set()) == ["email"]


def test_scrubs_sa_id():
    out = scrub_text("His ID is 0001010000089 okay", set())
    assert "0001010000089" not in out and "[id]" in out


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


# --- SA ID detection must not fire on WMS identifiers ---------------------------------
# Illustrative subjects: "IN-000000 EXDC WMOS Wave Abort <13 digits> - urgent issue" and
# "JC<13 digits>". Bare \d{13} held both cards as PII, withholding legitimate entries.

VALID_SA_ID = "9001015009086"     # synthetic: valid YYMMDD prefix and Luhn checksum


def test_a_real_sa_id_is_still_detected():
    assert "sa_id" in leaks(f"the operator id is {VALID_SA_ID} on file", set())


def test_a_real_sa_id_is_still_scrubbed():
    assert VALID_SA_ID not in scrub_text(f"id {VALID_SA_ID} here", set())


def test_a_wms_identifier_is_not_mistaken_for_an_sa_id():
    # fails the date prefix (month 87) and the checksum
    assert "sa_id" not in leaks("WMOS Wave Abort 9999999999999 - urgent", set())


def test_a_13_digit_number_with_a_valid_date_but_bad_checksum_is_not_an_id():
    bad = VALID_SA_ID[:-1] + ("0" if VALID_SA_ID[-1] != "0" else "1")
    assert "sa_id" not in leaks(f"reference {bad}", set())

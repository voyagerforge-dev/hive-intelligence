from hivezendesk.model import Comment, IssueCard, Ticket


def test_ticket_thread_text_joins_description_and_comments():
    t = Ticket(id=14872, subject="Orders not allocating", description="Wave stuck.",
               org_id=10000000000001, client="alpha", closed_at="2026-03-14T09:00:00Z",
               tags=["allocation"],
               comments=[Comment(author_role="agent", public=True, body="Replen lagged.",
                                 created_at="2026-03-14T10:00:00Z")])
    text = t.thread_text()
    assert "Wave stuck." in text
    assert "Replen lagged." in text
    assert t.slug_source() == "Orders not allocating"


def test_issue_card_path_is_ticket_id_prefixed():
    c = IssueCard(ticket_id=14872, client="alpha", title="Wave allocation stalls",
                  description="d", module="allocation", related=[], tags=[],
                  what_happened="w", how_it_closed="h", closed_at="2026-03-14")
    assert c.filename() == "14872-wave-allocation-stalls.md"

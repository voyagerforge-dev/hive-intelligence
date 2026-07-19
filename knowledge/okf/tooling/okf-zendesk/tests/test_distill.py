import json

from okfzendesk.distill import distill
from okfzendesk.model import Comment, Ticket


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.seen_user = None

    def complete(self, system, user):
        self.seen_user = user
        return self.payload


def _ticket():
    return Ticket(id=14872, subject="Orders not allocating",
                  description="Wave stuck; jane.doe@alpha.invalid reported it.",
                  org_id=1, client="alpha", closed_at="2026-03-14T09:00:00Z", tags=["allocation"],
                  comments=[Comment("agent", True, "Replen lagged; reran replenishment.",
                                    "2026-03-14T10:00:00Z")])


GOOD = json.dumps({"what_happened": "Morning wave did not allocate; replen lagged demand.",
                   "how_it_closed": "Reran replenishment; wave allocated.",
                   "module": "allocation", "tags": ["allocation", "replenishment"],
                   "related_candidates": ["wms/allocation/wave-replen-lag"],
                   "recurring": False})


def test_distill_returns_card_and_never_sends_pii_to_the_model():
    llm = FakeLLM(GOOD)
    card = distill(_ticket(), llm, known={"jane.doe@alpha.invalid"})
    assert card is not None
    assert card.ticket_id == 14872 and card.client == "alpha"
    assert card.module == "allocation"
    assert card.status == "distilled"
    assert card.what_happened.startswith("Morning wave")
    assert card.title == "Orders not allocating"      # ticket subject, not generated
    assert card.closed_at == "2026-03-14"
    assert "jane.doe@alpha.invalid" not in llm.seen_user


def test_distill_returns_none_on_malformed_output():
    assert distill(_ticket(), FakeLLM("not json at all"), known=set()) is None


def test_distill_returns_none_when_required_field_missing():
    bad = json.dumps({"title": "t"})
    assert distill(_ticket(), FakeLLM(bad), known=set()) is None


def test_distill_tolerates_fenced_and_thinking_output():
    fenced = f"<think>pondering</think>\n```json\n{GOOD}\n```"
    assert distill(_ticket(), FakeLLM(fenced), known=set()) is not None


def test_empty_how_it_closed_is_allowed():
    """Many tickets never state how they ended; that must not discard the entry."""
    payload = json.loads(GOOD)
    payload["how_it_closed"] = ""
    card = distill(_ticket(), FakeLLM(json.dumps(payload)), known=set())
    assert card is not None and card.how_it_closed == ""


def test_missing_module_is_rejected():
    """module is the alerting surface: without it the entry cannot be matched."""
    payload = json.loads(GOOD)
    payload["module"] = ""
    assert distill(_ticket(), FakeLLM(json.dumps(payload)), known=set()) is None


def test_recurring_flag_is_carried():
    payload = json.loads(GOOD)
    payload["recurring"] = True
    assert distill(_ticket(), FakeLLM(json.dumps(payload)), known=set()).recurring is True

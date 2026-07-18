import httpx
import pytest
import respx

from okfzendesk.fetch import ConnectorClient, to_ticket
from okfzendesk.model import RunError

BASE = "http://conn:8014"


@respx.mock
def test_list_closed_sends_bearer_and_params():
    route = respx.get(f"{BASE}/tickets/closed").mock(
        return_value=httpx.Response(200, json=[{"id": 1}]))
    c = ConnectorClient(BASE, "k", page_cap=3000, cap_warn_ratio=0.95)
    out = c.list_closed(org_id=42, since="2026-01-01")
    assert out == [{"id": 1}]
    req = route.calls[0].request
    assert req.headers["Authorization"] == "Bearer k"
    assert "org_id=42" in str(req.url) and "since=2026-01-01" in str(req.url)


@respx.mock
def test_at_cap_result_raises_so_caller_narrows_window():
    respx.get(f"{BASE}/tickets/closed").mock(
        return_value=httpx.Response(200, json=[{"id": i} for i in range(3000)]))
    c = ConnectorClient(BASE, "k", page_cap=3000, cap_warn_ratio=0.95)
    with pytest.raises(RunError, match="cap"):
        c.list_closed(org_id=42, since="2026-01-01")


@respx.mock
def test_get_ticket_requests_comments():
    route = respx.get(f"{BASE}/tickets/7").mock(
        return_value=httpx.Response(200, json={"id": 7, "comments": []}))
    c = ConnectorClient(BASE, "k")
    assert c.get_ticket(7)["id"] == 7
    assert "with_comments=true" in str(route.calls[0].request.url)


def test_to_ticket_maps_closed_at_from_updated_at():
    raw = {"id": 7, "subject": "s", "description": "d", "organization_id": 99,
           "updated_at": "2026-03-14T09:00:00Z", "tags": ["a"], "requester_id": 5}
    comments = [{"author_id": 5, "public": True, "body": "user says",
                 "created_at": "2026-03-14T09:00:00Z"},
                {"author_id": 8, "public": True, "body": "agent says",
                 "created_at": "2026-03-14T10:00:00Z"}]
    t = to_ticket(raw, client="alpha", comments=comments)
    assert t.closed_at == "2026-03-14T09:00:00Z"
    assert t.org_id == 99 and t.client == "alpha"
    assert [c.author_role for c in t.comments] == ["end-user", "agent"]

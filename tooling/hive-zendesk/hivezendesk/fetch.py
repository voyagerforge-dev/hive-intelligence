"""Read-only access to the live Zendesk connector. GET only, by contract.

The connector caps a pull at max_pages*page_size (3000) and returns truncated results
WITHOUT erroring. Silent loss looks like success, so an at-cap result is raised here and
the caller narrows the `since` window instead.
"""
from __future__ import annotations

import httpx

from . import USER_AGENT
from .model import Comment, RunError, Ticket


class ConnectorClient:
    def __init__(self, base: str, api_key: str, page_cap: int = 3000,
                 cap_warn_ratio: float = 0.95, timeout_s: int = 60) -> None:
        self._base = base.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}",
                         "User-Agent": USER_AGENT}
        self._page_cap = page_cap
        self._cap_threshold = int(page_cap * cap_warn_ratio)
        self._timeout = timeout_s

    def _get(self, path: str, params: dict) -> list | dict:
        r = httpx.get(f"{self._base}{path}", headers=self._headers,
                      params=params, timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    def list_closed(self, org_id: int, since: str) -> list[dict]:
        data = self._get("/tickets/closed", {"org_id": org_id, "since": since})
        rows = data if isinstance(data, list) else []
        if len(rows) >= self._cap_threshold:
            raise RunError(
                f"connector returned {len(rows)} tickets for org {org_id} since {since}, "
                f"at or near the {self._page_cap} page cap - results may be silently "
                f"truncated; narrow the window")
        return rows

    def get_ticket(self, ticket_id: int) -> dict:
        data = self._get(f"/tickets/{ticket_id}", {"with_comments": "true"})
        return data if isinstance(data, dict) else {}


def to_ticket(raw: dict, client: str, comments: list[dict]) -> Ticket:
    """Map a raw Zendesk ticket. closed_at comes from updated_at, per the archived mapper."""
    requester_id = raw.get("requester_id")
    mapped = [
        Comment(
            author_role="end-user" if c.get("author_id") == requester_id else "agent",
            public=bool(c.get("public", True)),
            body=c.get("body") or "",
            created_at=c.get("created_at") or "",
        )
        for c in (comments or [])
    ]
    return Ticket(
        id=int(raw["id"]),
        subject=raw.get("subject") or "",
        description=raw.get("description") or "",
        org_id=int(raw.get("organization_id") or 0),
        client=client,
        closed_at=raw.get("updated_at") or "",
        tags=list(raw.get("tags") or []),
        comments=mapped,
    )

"""Deterministic pre-LLM value gate. Every drop returns a reason so the filter is auditable.

Status is deliberately NOT checked: the connector only returns closed tickets, so a status
check here would be dead code.
"""
from __future__ import annotations

import hashlib
import re

from .model import Ticket

MIN_THREAD_CHARS = 120

_NOISE = re.compile(
    r"\b(password reset|reset my password|access request|grant (me )?access|"
    r"please rerun|re-?run the job|kindly rerun|unlock (my )?account|"
    r"add (me|user) to|new user request)\b",
    re.IGNORECASE,
)

# A resolution that is only an acknowledgement carries no knowledge.
_ACK_ONLY = re.compile(r"^\W*(done|fixed|resolved|closed|ok|thanks|thank you)\W*$", re.IGNORECASE)


def content_hash(t: Ticket) -> str:
    basis = f"{t.client}|{(t.subject or '').strip().lower()}|{(t.description or '').strip().lower()}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def keep(t: Ticket, seen_hashes: set[str]) -> tuple[bool, str]:
    """Return (True, "") to card this ticket, or (False, reason) to skip it."""
    if content_hash(t) in seen_hashes:
        return False, "duplicate"

    text = t.thread_text()
    if _NOISE.search(f"{t.subject or ''} {t.description or ''}"):
        return False, "noise-pattern"
    if len(text) < MIN_THREAD_CHARS:
        return False, "thin-content"

    agent_bodies = [
        c.body.strip() for c in t.comments if c.author_role == "agent" and c.body.strip()
    ]
    if not agent_bodies:
        return False, "no-diagnosis"
    if all(_ACK_ONLY.match(b) for b in agent_bodies):
        return False, "no-diagnosis"
    return True, ""

"""Core types. No I/O, no dependencies on other hivezendesk modules."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


class RunError(RuntimeError):
    """Raised when the verification gate fails. Never swallowed."""


def slugify(text: str, max_len: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:max_len].rstrip("-")) or "issue"


@dataclass(frozen=True)
class Comment:
    author_role: str          # "agent" | "end-user"
    public: bool
    body: str
    created_at: str


@dataclass(frozen=True)
class Ticket:
    id: int
    subject: str
    description: str
    org_id: int
    client: str               # "alpha" | "beta"
    closed_at: str            # mapped from updated_at
    tags: list[str] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)

    def thread_text(self) -> str:
        parts = [self.subject or "", self.description or ""]
        parts += [c.body or "" for c in self.comments]
        return "\n\n".join(p for p in parts if p.strip())

    def slug_source(self) -> str:
        return self.subject or f"ticket-{self.id}"


@dataclass
class IssueCard:
    """A journal entry, not a knowledge card: what happened at this client and where,
    pointing at the concept cards that explain the behaviour rather than restating it."""

    ticket_id: int
    client: str
    title: str
    description: str
    module: str
    related: list[str]
    tags: list[str]
    what_happened: str
    how_it_closed: str
    closed_at: str
    # Named for what the model is actually asked: is this a routine scheduled request
    # rather than a fault? It is NOT a measure of how often the issue recurs, and the
    # old name `recurring` was read that way by both skills and humans.
    routine: bool = False
    status: str = "distilled"
    model: str = ""   # which LLM produced this entry
    # Facets. Empty until relink decides them from the entry's own evidence, since which
    # products exist is corpus vocabulary rather than something this package can know.
    product: str = ""
    platform: str = ""

    def filename(self) -> str:
        return f"{self.ticket_id}-{slugify(self.title)}.md"


@dataclass
class RunReport:
    fetched: int = 0
    skipped: int = 0
    emitted: int = 0
    preserved: int = 0        # approved cards left untouched
    cached: int = 0           # already carded; not re-fetched, not re-distilled
    pii_held: int = 0         # quarantined before writing, never emitted
    failed: int = 0           # per-ticket errors, isolated
    skipped_reasons: list[tuple[int, str]] = field(default_factory=list)
    # (ticket_id, [kinds]) - kinds only, never the offending values
    pii_tickets: list[tuple[int, list[str]]] = field(default_factory=list)
    failures: list[tuple[int, str]] = field(default_factory=list)
    at_cap_slices: list[str] = field(default_factory=list)

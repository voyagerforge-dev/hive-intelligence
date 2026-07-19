"""Scrubbed ticket thread -> a thin JOURNAL ENTRY.

Deliberately NOT a knowledge card. The concept corpus (996 cards) and the db-object tier
already explain how WMOS behaves; re-stating that per ticket would duplicate it at scale
and dilute retrieval. A journal entry exists to make a consultant *aware* that this area
has bitten this client before, and to point at the concept card that explains why.

So an entry carries: what happened, where it happened (module + related cards), and how it
was closed - in one or two lines each. The explanation lives in the card it links to.

Returns None on any failure; callers treat None as "skip this ticket" so a model blip
never silently produces a bad entry.
"""
from __future__ import annotations

from .llm import ChatLLM, extract_json
from .model import IssueCard, Ticket
from .scrub import scrub_text

# `module` and `what_happened` are the alerting surface: without them an entry cannot be
# matched to what a consultant is doing, which is the entry's whole purpose.
REQUIRED = ("what_happened", "module")

SYSTEM = (
    "You write a one-entry incident JOURNAL line for a Manhattan WMOS consultancy, from a "
    "resolved support ticket. Reply with ONE JSON object and nothing else.\n"
    "Keys: what_happened (one sentence), how_it_closed (one sentence, empty string if the "
    "ticket does not say), module (the WMOS functional area, lowercase, e.g. allocation, "
    "replenishment, inbound, cycle-count, interfaces, wave), tags (array of short "
    "lowercase keywords), routine (true if this is a routine scheduled request rather "
    "than a fault).\n"
    "DO NOT explain how WMOS works - that is documented elsewhere and repeating it is "
    "worse than useless. Record only what happened at this site and how it ended.\n"
    "Write generic, reusable text. STRIP ALL PII: no person names, email addresses, phone "
    "numbers, ID numbers or account identifiers - refer to roles instead (for example "
    "'the site supervisor'). State only what the ticket supports; never invent a cause."
)

# Journal entries need far less of the thread than a knowledge card would: the opening
# report and the closing exchange carry the signal, the middle is usually back-and-forth.
MAX_THREAD_CHARS = 6000


def build_prompt(t: Ticket, known: set[str]) -> str:
    thread = scrub_text(t.thread_text(), known)
    if len(thread) > MAX_THREAD_CHARS:
        head = thread[: MAX_THREAD_CHARS // 2]
        tail = thread[-MAX_THREAD_CHARS // 2:]
        thread = f"{head}\n\n[...truncated...]\n\n{tail}"
    tags = ", ".join(t.tags) if t.tags else "(none)"
    return f"Client: {t.client}\nZendesk tags: {tags}\n\nTicket thread:\n{thread}"


def distill(t: Ticket, llm: ChatLLM, known: set[str]) -> IssueCard | None:
    raw = llm.complete(SYSTEM, build_prompt(t, known))
    data = extract_json(raw or "")
    if not data:
        return None
    if any(not str(data.get(k, "")).strip() for k in REQUIRED):
        return None

    what = str(data["what_happened"]).strip()
    closed = str(data.get("how_it_closed", "")).strip()
    subject = (t.subject or "").strip()
    return IssueCard(
        ticket_id=t.id,
        client=t.client,
        # The ticket's own subject is a better, cheaper title than a generated one, and
        # keeps the entry recognisable against the real Zendesk queue.
        title=subject or what[:80],
        description=what,
        module=str(data["module"]).strip().lower(),
        # Links are derived later by `relink`, against the real corpus: asking the
        # model for ids it has never seen produced a 4% hit rate.
        related=[],
        tags=[str(x).strip().lower() for x in (data.get("tags") or []) if str(x).strip()],
        what_happened=what,
        how_it_closed=closed,
        routine=bool(data.get("routine", False)),
        closed_at=(t.closed_at or "")[:10],
        model=getattr(llm, "model", ""),
    )

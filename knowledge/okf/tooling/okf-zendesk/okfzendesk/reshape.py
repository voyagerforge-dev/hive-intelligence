"""Existing staged card -> thin journal entry.

Cheaper than distilling from scratch: the input is a 300-700 byte card rather than a
multi-thousand-character ticket thread, so the model both reads and thinks less
(~20s vs ~39s per entry measured against the on-prem Qwen).

The old cards explain WMOS behaviour (Problem / Root cause / Resolution). A journal entry
deliberately does not: it records what happened at this site and points at the concept
cards. So this is a reshape plus a classification, not a re-summarisation.
"""
from __future__ import annotations

from .llm import ChatLLM, extract_json
from .model import IssueCard
from .r2 import StagedCard
from .scrub import scrub_text

REQUIRED = ("what_happened", "module")

SYSTEM = (
    "You convert an existing support knowledge card into ONE JSON journal index entry. "
    "Reply with ONE JSON object and nothing else.\n"
    "Keys: what_happened (one sentence), how_it_closed (one sentence, empty string if the "
    "card does not say), module (WMOS functional area, lowercase single token, e.g. "
    "allocation, replenishment, inbound, outbound, interfaces, labelling, wave, "
    "cycle-count, inventory, tasking), tags (3-6 short lowercase keywords), "
    "related_candidates (array of short topic slugs a reader should consult), "
    "recurring (true if this reads like a routine scheduled request rather than a fault).\n"
    "Do NOT explain how WMOS works - that is documented elsewhere and repeating it is worse "
    "than useless. Record only what happened at this site and how it ended. Be terse.\n"
    "STRIP ALL PII: no person names, email addresses, phone numbers, ID numbers or account "
    "identifiers - refer to roles instead."
)

MAX_CARD_CHARS = 4000


def reshape(staged: StagedCard, llm: ChatLLM, known: set[str],
            closed_at: str = "", subject: str = "") -> IssueCard | None:
    text = scrub_text(staged.text or "", known)[:MAX_CARD_CHARS]
    if not text.strip():
        return None

    data = extract_json(llm.complete(SYSTEM, text) or "")
    if not data:
        return None
    if any(not str(data.get(k, "")).strip() for k in REQUIRED):
        return None

    what = str(data["what_happened"]).strip()
    # Prefer the real ticket subject, then the card's own H1, then the summary line.
    title = (subject or staged.title() or what[:80]).strip()
    return IssueCard(
        ticket_id=staged.ticket_id,
        client=staged.client,
        title=title,
        description=what,
        module=str(data["module"]).strip().lower(),
        related=[str(x).strip() for x in (data.get("related_candidates") or []) if str(x).strip()],
        tags=[str(x).strip().lower() for x in (data.get("tags") or []) if str(x).strip()],
        what_happened=what,
        how_it_closed=str(data.get("how_it_closed", "")).strip(),
        recurring=bool(data.get("recurring", False)),
        closed_at=(closed_at or "")[:10],
    )

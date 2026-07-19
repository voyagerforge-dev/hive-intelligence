"""Existing staged card -> thin journal entry.

Cheaper than distilling from scratch: the input is a 300-700 byte card rather than a
multi-thousand-character ticket thread, so the model both reads and thinks less
(~20s vs ~39s per entry measured against the on-prem Qwen).

The old cards explain WMOS behaviour (Problem / Root cause / Resolution). A journal entry
deliberately does not: it records what happened at this site and points at the concept
cards. So this is a reshape plus a classification, not a re-summarisation.
"""
from __future__ import annotations

import json

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
    "routine (true if this is a routine scheduled request rather than a fault).\n"
    "Do NOT explain how WMOS works - that is documented elsewhere and repeating it is worse "
    "than useless. Record only what happened at this site and how it ended. Be terse.\n"
    "STRIP ALL PII: no person names, email addresses, phone numbers, ID numbers or account "
    "identifiers - refer to roles instead."
)

MAX_CARD_CHARS = 4000

# Batching exists purely to cut GPU work. The model is a reasoning model, so it spends
# ~1,300 tokens per entry when asked one at a time but ~540 when asked for five at once:
# it reasons about the batch rather than re-reasoning per card. Measured 2.4x fewer tokens
# per entry, which on a token-throughput-bound GPU is a 2.4x throughput gain.
BATCH_SYSTEM = (
    "For EACH numbered support card, emit one JSON object with keys what_happened, "
    "how_it_closed, module, tags, routine - the same fields and the "
    "same rules as for a single card. Reply with ONE JSON array of objects, in the same "
    "order as the cards, and nothing else.\n" + SYSTEM
)


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
        related=[],   # derived later by `relink` against the real corpus
        tags=[str(x).strip().lower() for x in (data.get("tags") or []) if str(x).strip()],
        what_happened=what,
        how_it_closed=str(data.get("how_it_closed", "")).strip(),
        routine=bool(data.get("routine", False)),
        closed_at=(closed_at or "")[:10],
        model=getattr(llm, "model", ""),
    )


def _card_from(data: dict, staged: StagedCard, closed_at: str, subject: str) -> IssueCard | None:
    if not isinstance(data, dict):
        return None
    if any(not str(data.get(k, "")).strip() for k in REQUIRED):
        return None
    what = str(data["what_happened"]).strip()
    return IssueCard(
        ticket_id=staged.ticket_id,
        client=staged.client,
        title=(subject or staged.title() or what[:80]).strip(),
        description=what,
        module=str(data["module"]).strip().lower(),
        related=[],   # derived later by `relink` against the real corpus
        tags=[str(x).strip().lower() for x in (data.get("tags") or []) if str(x).strip()],
        what_happened=what,
        how_it_closed=str(data.get("how_it_closed", "")).strip(),
        routine=bool(data.get("routine", False)),
        closed_at=(closed_at or "")[:10],
    )


def extract_array(text: str) -> list | None:
    """Pull the JSON array out of a batched reply, tolerating prose or fences around it."""
    t = (text or "").strip()
    start, end = t.find("["), t.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        arr = json.loads(t[start:end + 1])
    except json.JSONDecodeError:
        return None
    return arr if isinstance(arr, list) else None


def reshape_batch(batch: list[tuple[StagedCard, str, str]], llm: ChatLLM,
                  known: set[str]) -> list[IssueCard | None]:
    """Reshape several staged cards in one call.

    Falls back to one-at-a-time for the whole batch if the reply cannot be parsed or the
    object count does not match the cards sent - a misaligned array would silently attach
    one ticket's summary to another ticket's id, which is far worse than being slow.
    """
    if not batch:
        return []
    if len(batch) == 1:
        staged, closed_at, subject = batch[0]
        return [reshape(staged, llm, known, closed_at, subject)]

    parts = []
    for i, (staged, _, _) in enumerate(batch, 1):
        text = scrub_text(staged.text or "", known)[:MAX_CARD_CHARS]
        parts.append(f"### CARD {i}\n{text}")

    arr = extract_array(llm.complete(BATCH_SYSTEM, "\n\n".join(parts)) or "")
    if arr is None or len(arr) != len(batch):
        return [reshape(s, llm, known, c, sub) for s, c, sub in batch]

    cards = [_card_from(obj, s, c, sub) for obj, (s, c, sub) in zip(arr, batch, strict=True)]
    for c_ in cards:
        if c_ is not None:
            c_.model = getattr(llm, "model", "")
    return cards

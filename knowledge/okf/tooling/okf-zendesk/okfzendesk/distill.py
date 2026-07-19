"""Scrubbed ticket thread -> structured issue fields.

Returns None on any failure; callers treat None as "skip this ticket" so a model blip
never silently produces a bad card.
"""
from __future__ import annotations

from .llm import ChatLLM, extract_json
from .model import IssueCard, Ticket
from .scrub import scrub_text

# `diagnosis` is deliberately NOT required: the prompt tells the model to leave it empty
# when the ticket shows no root cause, so requiring it here would discard exactly those
# tickets as "distill-failed". The retired service made the same allowance for root_cause.
REQUIRED = ("title", "description", "module", "symptom", "resolution")

SYSTEM = (
    "You turn a resolved support ticket into a single factual knowledge card for a "
    "Manhattan WMOS consultancy. Reply with ONE JSON object and nothing else.\n"
    "Keys: title, description, module, tags (array), related_candidates (array of short "
    "topic slugs), symptom, diagnosis, resolution, context.\n"
    "Write generic, reusable text. STRIP ALL PII: do not include any person names, email "
    "addresses, phone numbers, ID numbers or account identifiers - describe roles and "
    "systems instead (for example 'the site supervisor', 'the interface user').\n"
    "State only what the ticket supports; never invent a cause or a fix. If the ticket "
    "does not show a root cause, set diagnosis to an empty string."
)

MAX_THREAD_CHARS = 12000


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
    return IssueCard(
        ticket_id=t.id,
        client=t.client,
        title=str(data["title"]).strip(),
        description=str(data["description"]).strip(),
        module=str(data["module"]).strip(),
        related=[str(x).strip() for x in (data.get("related_candidates") or []) if str(x).strip()],
        tags=[str(x).strip() for x in (data.get("tags") or []) if str(x).strip()],
        symptom=str(data["symptom"]).strip(),
        diagnosis=str(data["diagnosis"]).strip(),
        resolution=str(data["resolution"]).strip(),
        context=str(data.get("context", "")).strip(),
        closed_at=(t.closed_at or "")[:10],
    )

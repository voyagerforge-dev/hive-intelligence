"""Write client-scoped issue cards. Idempotent, and never destroys human-approved work.

Applies the okf-dbparse lesson structurally: a hard gate catches dropped content but not
rewritten content, so rewriting an approved card is prevented rather than detected.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from .model import IssueCard


def _frontmatter(card: IssueCard, version: str) -> dict:
    return {
        "type": "issue",
        "title": card.title,
        "description": card.description,
        "client": card.client,
        "product": "wms",
        "platform": "wmos",
        "module": card.module,
        "related": card.related,
        "tags": card.tags,
        "recurring": card.recurring,
        "sources": [{"kind": "zendesk-ticket", "ref": str(card.ticket_id),
                     "closed": card.closed_at}],
        "status": card.status,
        "distilled_by": f"okf-zendesk@{version}",
        "timestamp": date.today().isoformat(),
    }


def render(card: IssueCard, version: str) -> str:
    fm = yaml.safe_dump(_frontmatter(card, version), sort_keys=False, allow_unicode=True,
                        default_flow_style=False).strip()
    # Deliberately terse. This is a pointer, not an explanation: the concept cards in
    # `related` carry the product behaviour, and duplicating it here would dilute them.
    body = [f"---\n{fm}\n---\n", f"## What happened\n\n{card.what_happened}\n"]
    if card.how_it_closed:
        body.append(f"## How it closed\n\n{card.how_it_closed}\n")
    if card.related:
        links = "\n".join(f"- `{r}`" for r in card.related)
        body.append(f"## See also\n\n{links}\n")
    return "\n".join(body)


def card_dir(clients_dir: str | Path, client: str) -> Path:
    return Path(clients_dir) / client / "issues"


def existing_card_path(clients_dir: str | Path, card: IssueCard) -> Path | None:
    """Any card already written for this ticket, regardless of its slug.

    The slug comes from an LLM-generated title, which can drift between runs. Matching on
    the ticket-id prefix keeps one ticket bound to one file, so a reworded title updates
    the existing card instead of silently creating a duplicate.
    """
    d = card_dir(clients_dir, card.client)
    if not d.exists():
        return None
    hits = sorted(d.glob(f"{card.ticket_id}-*.md"))
    return hits[0] if hits else None


def write_card(clients_dir: str | Path, card: IssueCard, version: str,
               force: bool = False) -> tuple[Path, str]:
    """Returns (path, "written" | "unchanged" | "preserved")."""
    d = card_dir(clients_dir, card.client)
    d.mkdir(parents=True, exist_ok=True)
    path = existing_card_path(clients_dir, card) or (d / card.filename())
    body = render(card, version)

    if path.exists():
        existing = path.read_text()
        if "status: approved" in existing and not force:
            return path, "preserved"
        if existing == body:
            return path, "unchanged"
    path.write_text(body)
    return path, "written"

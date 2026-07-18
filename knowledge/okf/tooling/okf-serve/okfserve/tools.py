"""Transport-agnostic read tools over the OKF resolver."""
from __future__ import annotations

from okfserve.resolver import get_card, load_index, resolve


def list_concepts(concepts_dir, clients_dir=None, client=None) -> list[dict]:
    out = []
    for c in load_index(concepts_dir, clients_dir):
        if c.get("type") == "correction":
            continue
        # Client-scoped cards (memory, distilled issues) surface only for their own
        # client, so a general concept listing is never diluted by them.
        if c.get("type") in ("memory", "issue") and (client is None or c.get("client") != client):
            continue
        out.append(c)
    return out


def get_card_text(concepts_dir, card_id: str, clients_dir=None) -> str:
    text = get_card(concepts_dir, card_id, clients_dir)
    return text if text is not None else f"No card found with id '{card_id}'."


def resolve_cards(concepts_dir, ids, depth: int = 1, max_cards: int = 8, max_chars: int | None = None,
                  clients_dir=None, client=None) -> dict:
    return resolve(concepts_dir, list(ids), depth=depth, max_cards=max_cards, max_chars=max_chars,
                   clients_dir=clients_dir, client=client)

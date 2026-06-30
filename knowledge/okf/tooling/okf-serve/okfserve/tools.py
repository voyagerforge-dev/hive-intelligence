"""Transport-agnostic read tools over the OKF resolver."""
from __future__ import annotations

from okfserve.resolver import get_card, load_index, resolve


def list_concepts(concepts_dir) -> list[dict]:
    return load_index(concepts_dir)


def get_card_text(concepts_dir, card_id: str) -> str:
    text = get_card(concepts_dir, card_id)
    return text if text is not None else f"No card found with id '{card_id}'."


def resolve_cards(concepts_dir, ids, depth: int = 1, max_cards: int = 8, max_chars: int | None = None) -> dict:
    return resolve(concepts_dir, list(ids), depth=depth, max_cards=max_cards, max_chars=max_chars)

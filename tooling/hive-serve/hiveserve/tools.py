"""Transport-agnostic read tools over the OKF resolver."""
from __future__ import annotations

from hiveserve.resolver import get_card, load_index, resolve

_LEAN_FIELDS = ("id", "title", "product", "type", "regime", "version",
                "client", "corrects", "status")


def list_concepts(concepts_dir, clients_dir=None, client=None, product=None) -> list[dict]:
    out = []
    for c in load_index(concepts_dir, clients_dir):
        if c.get("type") == "correction":
            continue
        # Client-scoped cards (memory, distilled issues) surface only for their own
        # client, so a general concept listing is never diluted by them.
        if c.get("type") in ("memory", "issue") and (client is None or c.get("client") != client):
            continue
        if product is not None and c.get("product") != product:
            continue
        # Lean rows only, and null keys omitted. The description is what balloons this
        # (990 cards -> ~109K tokens, over the client cap); the always-null facets add
        # another ~40%. A concept card keeps just id/title/product/type. Use find_concepts
        # for a topic search that returns descriptions for the matched set.
        out.append({k: c.get(k) for k in _LEAN_FIELDS if c.get(k) is not None})
    return out


def find_concepts(concepts_dir, query, clients_dir=None, product=None, limit=20) -> list[dict]:
    """Keyword search over concept cards by title / description / id.

    Mirrors find_db_objects: a broad or topic question ("explain the architecture") should
    never dump the whole 990-card index. This returns a small, ranked set, with the
    description kept for the matches so the model can choose which ids to resolve.
    """
    tokens = [t for t in query.lower().split() if t]
    if not tokens:
        return []
    hits = []
    for c in load_index(concepts_dir, clients_dir):
        if c.get("type") != "concept":
            continue
        if product is not None and c.get("product") != product:
            continue
        hay = " ".join([c.get("title") or "", c.get("description") or "",
                        c.get("id") or ""]).lower()
        score = sum(1 for t in tokens if t in hay)
        if score > 0:
            hits.append((score, c))
    hits.sort(key=lambda sc: (-sc[0], sc[1].get("id") or ""))
    return [{"id": c.get("id"), "title": c.get("title"), "product": c.get("product"),
             "description": c.get("description")} for _, c in hits[:limit]]


def get_card_text(concepts_dir, card_id: str, clients_dir=None) -> str:
    text = get_card(concepts_dir, card_id, clients_dir)
    return text if text is not None else f"No card found with id '{card_id}'."


def resolve_cards(concepts_dir, ids, depth: int = 1, max_cards: int = 8, max_chars: int | None = None,
                  clients_dir=None, client=None) -> dict:
    return resolve(concepts_dir, list(ids), depth=depth, max_cards=max_cards, max_chars=max_chars,
                   clients_dir=clients_dir, client=client)

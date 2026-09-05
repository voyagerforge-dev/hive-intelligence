"""Transport-agnostic read tools over the OKF resolver."""
from __future__ import annotations

from hiveserve.ranking import rank
from hiveserve.resolver import get_card, load_index, out_of_client_scope, resolve

_LEAN_FIELDS = ("id", "title", "product", "type", "regime", "version",
                "client", "corrects", "status")


def list_concepts(concepts_dir, clients_dir=None, client=None, product=None) -> list[dict]:
    out = []
    for c in load_index(concepts_dir, clients_dir):
        if c.get("type") == "correction":
            continue
        # Client-scoped cards (memory, distilled issues) surface only for their own
        # client, so a general concept listing is never diluted by them.
        if out_of_client_scope(c, client):
            continue
        if product is not None and c.get("product") != product:
            continue
        # Lean rows only, and null keys omitted. The description is what balloons this
        # (990 cards -> ~109K tokens, over the client cap); the always-null facets add
        # another ~40%. A concept card keeps just id/title/product/type. Use find_concepts
        # for a topic search that returns descriptions for the matched set.
        out.append({k: c.get(k) for k in _LEAN_FIELDS if c.get(k) is not None})
    return out


def find_concepts(concepts_dir, query, clients_dir=None, product=None, limit=20,
                  client=None) -> list[dict]:
    """Rank topic matches without sending the whole catalogue to the agent.

    Descriptions let the caller choose which ids to resolve. The public search contract
    is in docs/reference/hive-serve.md#search; scoring details live in ranking.py.
    """
    candidates = [c for c in load_index(concepts_dir, clients_dir)
                  if (c.get("type") == "concept"
                      or (c.get("type") == "memory" and not out_of_client_scope(c, client)))
                  and (product is None or c.get("product") == product)]
    # Document frequencies come from `candidates`, so idf describes the collection actually
    # being searched. That is also the whole index this call already loaded: there is no
    # cached or precomputed state anywhere behind this function.
    hits = rank(query, candidates, limit)
    # Keep the transport shape stable; a memory id already identifies its client.
    return [{"id": c.get("id"), "title": c.get("title"), "product": c.get("product"),
             "description": c.get("description")} for c in hits]


def get_card_text(concepts_dir, card_id: str, clients_dir=None) -> str:
    text = get_card(concepts_dir, card_id, clients_dir)
    return text if text is not None else f"No card found with id '{card_id}'."


def resolve_cards(concepts_dir, ids, depth: int = 1, max_cards: int = 8, max_chars: int | None = None,
                  clients_dir=None, client=None) -> dict:
    resolved = resolve(concepts_dir, list(ids), depth=depth, max_cards=max_cards, max_chars=max_chars,
                       clients_dir=clients_dir, client=client)
    return {key: resolved[key] for key in ("card_ids", "bundle", "dropped", "corrections")}

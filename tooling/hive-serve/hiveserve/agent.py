"""Grounded-Q&A agent that draws context directly from the OKF bundle (no RAG)."""
from __future__ import annotations

from hivegen.llm import extract_json

from hiveserve.resolver import load_index, out_of_client_scope, resolve

_SELECT_SYS = (
    "You are given an INDEX of knowledge-card ids with titles and descriptions, and a QUESTION. "
    "Choose the card id(s) whose content best answers the question. "
    "Some cards carry a product facet, shown as {product}. First decide which product the "
    "QUESTION is about, then pick ONLY cards of that product plus any untagged "
    "(product-neutral) cards; never mix products. "
    "Some cards are tagged with a regime, [ops] (OPS / Order Planning Strategy) or [traditional] "
    "(standalone replenishment/tasking/fulfilment). OPS and traditional are MUTUALLY EXCLUSIVE by "
    "site configuration: first decide which regime the QUESTION is about, then pick ONLY cards of "
    "that regime plus untagged (regime-neutral) cards. Never pick a card tagged the other regime, "
    "e.g. for an OPS question do not pick [traditional] cards even if their keywords match. "
    "Some cards are tagged with a release version like (v2020). If the QUESTION names a release, "
    "PREFER cards for that release plus version-neutral (untagged) cards, and avoid cards tagged only "
    "for a different release, but a version-neutral card always applies, and do not exclude a "
    "different-release card if nothing better answers the question. "
    "Some cards are client-specific MEMORY, tagged like <client:alpha>. Memory applies ONLY to that "
    "client, it records how THAT client's system was modified, not vanilla product behaviour. Pick a "
    "client-memory card ONLY when the QUESTION is about that same client; never pick another client's "
    "memory, and never use memory as general product knowledge. "
    'Reply with ONLY {"card_ids": ["<id>", ...]} using ids from the index verbatim.'
)

_ANSWER_SYS = (
    "Answer the QUESTION using ONLY the provided knowledge cards. Be specific and preserve "
    "exact fields, codes, and table/column names. Ground every claim and cite the source file "
    "from a card's `sources:` in square brackets, e.g. [some-doc.md]. If the cards do not "
    "contain the answer, say so explicitly. "
    "Some knowledge cards are followed by CORRECTION cards that target them (type: correction). "
    "A correction is AUTHORITATIVE: ground your answer in the corrected fact and note the correction; "
    "do NOT repeat a statement the correction contradicts. "
    "Some knowledge cards are client-specific MEMORY (type: memory, client: <name>). A memory card "
    "describes how THAT client's system behaves after a modification; it is NOT general product fact. "
    "Use it only for that client and never generalise it to core product behaviour or another client. "
)


def _index_text(index: list[dict]) -> str:
    def tag(c):
        cl = f"<client:{c['client']}> " if c.get("client") else ""
        p = f"{{{c['product']}}} " if c.get("product") else ""
        r = f"[{c['regime']}] " if c.get("regime") else ""
        v = f"(v{','.join(c['version'])}) " if c.get("version") else ""
        return cl + p + r + v
    return "\n".join(f"- {c['id']}: {tag(c)}{c['title']}, {c['description']}" for c in index)


def select_ids(index, question: str, llm, *, known_ids: set[str]) -> list[str]:
    user = f"INDEX:\n{_index_text(index)}\n\nQUESTION: {question}"
    for _ in range(2):
        data = extract_json(llm.complete(_SELECT_SYS, user) or "")
        ids = [i for i in (data or {}).get("card_ids", []) if i in known_ids]
        if ids:
            return ids
    return []


def answer_question(concepts_dir, question, *, select_llm, answer_llm,
                    mode: str = "progressive", depth: int = 1, max_cards: int = 8,
                    max_chars: int | None = None, clients_dir=None, client=None) -> dict:
    from hiveserve.resolver import corrections_by_target
    index = load_index(concepts_dir, clients_dir)
    corr_map = corrections_by_target(index)
    # Exactly `tools.list_concepts`'s filter, through the same predicate. This used to
    # name `memory` alone, so every client's issue cards - 2,295 of them on a measured
    # corpus, two thirds of a 215,000-token prompt - were listed to the selector on every
    # question, whichever client was asking and even when none was. Selection integrity
    # survived it, because `resolve` refuses an out-of-scope id, but client-confidential
    # titles and descriptions were sent to the model gateway each time.
    concepts = [c for c in index
                if c.get("type") != "correction" and not out_of_client_scope(c, client)]
    if mode == "ceiling":
        selected = [c["id"] for c in concepts]
        resolved = resolve(concepts_dir, selected, depth=0, max_cards=len(selected) or 1,
                           corrections=corr_map, clients_dir=clients_dir, client=client)
    else:
        selected = select_ids(concepts, question, select_llm, known_ids={c["id"] for c in concepts})
        resolved = resolve(concepts_dir, selected, depth=depth, max_cards=max_cards,
                           max_chars=max_chars, corrections=corr_map,
                           clients_dir=clients_dir, client=client)
    user = f"KNOWLEDGE CARDS:\n{resolved['bundle']}\n\nQUESTION: {question}"
    answer = answer_llm.complete(_ANSWER_SYS, user) or ""
    return {"answer": answer, "selected_ids": selected,
            "bundle_ids": resolved["card_ids"], "mode": mode}

"""Grounded-Q&A agent that draws context directly from the OKF bundle (no RAG)."""
from __future__ import annotations

from okfgen.llm import extract_json

from okfserve.resolver import load_index, resolve

_SELECT_SYS = (
    "You are given an INDEX of knowledge-card ids with titles and descriptions, and a QUESTION. "
    "Choose the card id(s) whose content best answers the question. "
    "Some cards are tagged with a regime — [ops] (OPS / Order Planning Strategy) or [traditional] "
    "(standalone replenishment/tasking/fulfilment). OPS and traditional are MUTUALLY EXCLUSIVE by "
    "site configuration: first decide which regime the QUESTION is about, then pick ONLY cards of "
    "that regime plus untagged (regime-neutral) cards. Never pick a card tagged the other regime — "
    "e.g. for an OPS question do not pick [traditional] cards even if their keywords match. "
    'Reply with ONLY {"card_ids": ["<id>", ...]} using ids from the index verbatim.'
)

_ANSWER_SYS = (
    "Answer the QUESTION using ONLY the provided knowledge cards. Be specific and preserve "
    "exact fields, codes, and table/column names. Ground every claim and cite the source file "
    "from a card's `sources:` in square brackets, e.g. [some-doc.md]. If the cards do not "
    "contain the answer, say so explicitly."
)


def _index_text(index: list[dict]) -> str:
    def tag(c):
        r = f"[{c['regime']}] " if c.get("regime") else ""
        v = f"(v{','.join(c['version'])}) " if c.get("version") else ""
        return r + v
    return "\n".join(f"- {c['id']}: {tag(c)}{c['title']} — {c['description']}" for c in index)


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
                    max_chars: int | None = None) -> dict:
    index = load_index(concepts_dir)
    if mode == "ceiling":
        selected = [c["id"] for c in index]
        resolved = resolve(concepts_dir, selected, depth=0, max_cards=len(selected) or 1)
    else:
        selected = select_ids(index, question, select_llm, known_ids={c["id"] for c in index})
        resolved = resolve(concepts_dir, selected, depth=depth, max_cards=max_cards,
                           max_chars=max_chars)
    user = f"KNOWLEDGE CARDS:\n{resolved['bundle']}\n\nQUESTION: {question}"
    answer = answer_llm.complete(_ANSWER_SYS, user) or ""
    return {"answer": answer, "selected_ids": selected,
            "bundle_ids": resolved["card_ids"], "mode": mode}

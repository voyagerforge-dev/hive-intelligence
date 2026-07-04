"""Classify one OKF card into the OPS/traditional either-or (or 'none'). Templated on assign.py."""
from __future__ import annotations

from okfgen.facets import read_facets
from okfgen.llm import ChatLLM, extract_json

_LABELS = {"traditional", "ops", "none"}

_SYSTEM = (
    "You classify a Manhattan WMOS knowledge card by ORDER-FULFILMENT REGIME. When OPS (Order "
    "Planning Strategy / DC Order Planning) is active, standalone traditional replenishment, tasking, "
    "and wave/fulfilment are superseded by OPS-orchestrated Wave/Stream runs, and vice-versa. Label:\n"
    "- 'ops': the card describes OPS / DC Order Planning / Wave-Stream-run orchestration itself.\n"
    "- 'traditional': the card describes standalone replenishment/tasking/wave/fulfilment execution.\n"
    "- 'none': the card is outside this either-or (receiving, labour, yard, master data, labels, "
    "config that is regime-neutral, or a card that only *mentions* OPS in passing).\n"
    'Reply with ONLY {"label":"<traditional|ops|none>","rationale":"<one short reason>",'
    '"confidence":<0..1>}.'
)


def classify_card_regime(card_text: str, llm: ChatLLM) -> dict:
    fm = read_facets(card_text)
    user = (
        f"TITLE: {fm.get('title','')}\nDESCRIPTION: {fm.get('description','')}\n"
        f"TAGS: {fm.get('tags', [])}\n\nCARD:\n{card_text[:2000]}"
    )
    data = extract_json(llm.complete(_SYSTEM, user) or "")
    label = (data or {}).get("label")
    if label not in _LABELS:
        return {"label": "none", "rationale": "unparsed", "confidence": 0.0}
    try:
        conf = float((data or {}).get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    return {"label": label, "rationale": (data or {}).get("rationale", ""), "confidence": conf}

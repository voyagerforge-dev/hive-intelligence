"""Distill a concept's source docs into one OKF card (frontmatter + curated prose)."""
from __future__ import annotations

import yaml

from okfgen.llm import ChatLLM, extract_json
from okfgen.load import Doc
from okfgen.taxonomy import Concept

_SYSTEM = (
    "You convert several Manhattan WMOS reference documents about ONE concept into a single "
    "reusable knowledge card. Reply with ONLY a JSON object: "
    "{\"title\", \"description\", \"tags\", \"related\", \"body\"}. "
    "title: concise concept title. description: one sentence. tags: list of short tags. "
    "related: list of other concept ids/terms this links to. "
    "body: self-contained, reusable prose explaining the concept (the bulk of the value). "
    "Preserve specifics (parameters, rules); do not over-summarize."
)


def build_okf_card(meta: dict, body: str) -> str:
    frontmatter = yaml.safe_dump(meta, sort_keys=False).rstrip()
    return f"---\n{frontmatter}\n---\n\n{body.rstrip()}\n"


def distill_concept(concept: Concept, docs: list[Doc], llm: ChatLLM, *,
                    max_chars: int, today: str) -> str | None:
    combined = "\n\n".join(d.text for d in docs)[:max_chars]
    data = extract_json(llm.complete(_SYSTEM, combined) or "")
    if not data or not data.get("body", "").strip():
        return None
    meta = {
        "type": "concept",
        "title": data.get("title") or concept.title,
        "description": data.get("description", ""),
        "tags": data.get("tags", []),
        "resource": "wmos",
        "sources": [{"kind": "wms-doc", "ref": d.name} for d in docs],
        "related": data.get("related", []),
        "distilled_at": today,
        "status": "draft",
    }
    return build_okf_card(meta, data["body"])

"""Distill a concept's source docs into one OKF card (frontmatter + curated prose)."""
from __future__ import annotations

import yaml

from hivegen.llm import ChatLLM, extract_json
from hivegen.load import Doc
from hivegen.taxonomy import Concept

_SYSTEM = (
    "You convert several Manhattan WMOS reference documents about ONE concept into a single "
    "reusable knowledge card. Reply with ONLY a JSON object: "
    "{\"title\", \"description\", \"tags\", \"related\", \"body\"}. "
    "title: concise concept title. description: one sentence. tags: list of short tags. "
    "related: list of concept ids this links to — MUST be a subset of the ids provided in "
    "the user message (use only those exact ids, or an empty list). "
    "body: self-contained, reusable prose explaining the concept (the bulk of the value). "
    "Preserve specifics (parameters, rules); do not over-summarize."
)


def build_okf_card(meta: dict, body: str) -> str:
    frontmatter = yaml.safe_dump(meta, sort_keys=False).rstrip()
    return f"---\n{frontmatter}\n---\n\n{body.rstrip()}\n"


def distill_concept(concept: Concept, docs: list[Doc], llm: ChatLLM, *,
                    max_chars: int, today: str,
                    related_ids: list[str] | None = None) -> str | None:
    combined = "\n\n".join(d.text for d in docs)[:max_chars]
    if related_ids is not None:
        combined += (
            f"\n\nValid concept ids for the `related` field (choose only from these, or empty): "
            f"{', '.join(related_ids)}"
        )
    data = extract_json(llm.complete(_SYSTEM, combined) or "")
    if not data:
        return None
    body = data.get("body", "")
    if not isinstance(body, str) or not body.strip():
        return None
    related = [r for r in data.get("related", []) if r in set(related_ids or [])]
    meta = {
        "type": "concept",
        "title": data.get("title") or concept.title,
        "description": data.get("description", ""),
        "tags": data.get("tags", []),
        # `resource` is upgraded to the served-card URI, and `## Related`/`# Citations`
        # body sections are generated, by scripts/conformance_pass.py after promote+facet.
        "resource": "wmos",
        "sources": [{"kind": "wms-doc", "ref": d.name} for d in docs],
        "related": related,
        "distilled_at": today,
        "timestamp": today,  # OKF-recommended last-change field
        "status": "draft",
    }
    return build_okf_card(meta, body)

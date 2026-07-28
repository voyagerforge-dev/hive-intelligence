"""Assign each doc to one concept from the approved taxonomy (or 'exclude')."""
from __future__ import annotations

from hivegen.llm import ChatLLM, extract_json
from hivegen.load import Doc
from hivegen.taxonomy import Concept

_SYSTEM = (
    "You classify a reference document into exactly ONE concept from the provided list, "
    "or 'exclude' if it is instance-specific/junk not worth keeping as reusable knowledge. "
    "Reply with ONLY {\"concept_id\": \"<id-or-exclude>\"}."
)


def _prompt(doc: Doc, concepts: list[Concept], snippet_chars: int) -> str:
    options = "\n".join(f"- {c.id}: {c.title} ({c.description})" for c in concepts)
    return f"CONCEPTS:\n{options}\n\nDOCUMENT {doc.name}:\n{doc.text[:snippet_chars]}"


def classify_doc(doc: Doc, concepts: list[Concept], llm: ChatLLM, *, snippet_chars: int = 600) -> str:
    valid = {c.id for c in concepts} | {"exclude"}
    data = extract_json(llm.complete(_SYSTEM, _prompt(doc, concepts, snippet_chars)) or "")
    cid = (data or {}).get("concept_id", "exclude")
    return cid if cid in valid else "exclude"


def assign_docs(docs: list[Doc], concepts: list[Concept], llm: ChatLLM
                ) -> tuple[dict[str, list[str]], list[str]]:
    assignments: dict[str, list[str]] = {}
    excluded: list[str] = []
    for doc in docs:
        cid = classify_doc(doc, concepts, llm)
        if cid == "exclude":
            excluded.append(doc.id)
        else:
            assignments.setdefault(cid, []).append(doc.id)
    return assignments, excluded

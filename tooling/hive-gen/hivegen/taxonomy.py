"""Propose a Wave/Replenishment concept taxonomy from the doc inventory (LLM)."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from hivegen.llm import ChatLLM, extract_json
from hivegen.load import Doc

_SYSTEM = (
    "You are a Manhattan WMOS expert. Given a list of document titles and snippets from the "
    "Wave/Replenishment functional area, propose a FINE-GRAINED taxonomy of distinct CONCEPTS "
    "they cover. Reply with ONLY a JSON object: {\"concepts\": [{\"id\", \"title\", "
    "\"description\", \"aliases\"}]}. id is a short kebab-case slug; aliases is a list of "
    "alternative terms. "
    "Make ONE concept per distinct process, screen, algorithm, or configuration entity: aim for "
    "roughly 25-45 narrow, single-topic concepts, each mapping to about 1-4 source documents. "
    "Keep distinct sub-processes SEPARATE rather than lumping them: e.g. 'major/minor order "
    "creation', 'pre-wave filtering', '3D cubing', 'zone picking', 'lean-time replenishment', "
    "'activity tracking (FS-300) for replenishment' are each their own concept. Prefer many "
    "narrow concepts over a few broad buckets."
)


class Concept(BaseModel):
    id: str
    title: str
    description: str = ""
    aliases: list[str] = Field(default_factory=list)


def propose_taxonomy(docs: list[Doc], llm: ChatLLM, *, snippet_chars: int = 400) -> list[Concept]:
    inventory = "\n".join(f"- {d.name}: {d.text[:snippet_chars]}" for d in docs)
    data = extract_json(llm.complete(_SYSTEM, inventory) or "")
    if not data or "concepts" not in data:
        return []
    out: list[Concept] = []
    for c in data["concepts"]:
        try:
            out.append(Concept(**c))
        except (TypeError, ValueError):
            continue
    return out


def write_taxonomy(path: str | Path, concepts: list[Concept]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump({"concepts": [c.model_dump() for c in concepts]}, sort_keys=False))


def load_taxonomy(path: str | Path) -> list[Concept]:
    data = yaml.safe_load(Path(path).read_text()) or {}
    return [Concept(**c) for c in data.get("concepts", [])]

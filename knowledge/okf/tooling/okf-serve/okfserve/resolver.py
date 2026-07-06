"""No-RAG retrieval over an OKF bundle: index + direct load + cross-link traversal."""
from __future__ import annotations

from pathlib import Path

import yaml


def parse_frontmatter(text: str) -> dict:
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    fm = yaml.safe_load(parts[1])
    return fm if isinstance(fm, dict) else {}


def load_index(concepts_dir) -> list[dict]:
    out: list[dict] = []
    for p in sorted(Path(concepts_dir).glob("*.md")):
        if p.name == "index.md":
            continue
        fm = parse_frontmatter(p.read_text())
        out.append({"id": p.stem, "title": fm.get("title", p.stem),
                    "description": fm.get("description", ""),
                    "regime": fm.get("regime"), "type": fm.get("type", "concept"),
                    "version": fm.get("version")})
    return out


def get_card(concepts_dir, card_id: str) -> str | None:
    p = Path(concepts_dir) / f"{card_id}.md"
    return p.read_text() if p.exists() else None


def resolve(concepts_dir, ids: list[str], *, depth: int = 1, max_cards: int = 8,
            max_chars: int | None = None) -> dict:
    concepts_dir = Path(concepts_dir)
    selected: list[str] = []
    dropped: list[str] = []
    frontier = [i for i in ids if (concepts_dir / f"{i}.md").exists()]
    seen = set(frontier)
    level = 0
    while frontier:
        next_frontier: list[str] = []
        for cid in frontier:
            if len(selected) >= max_cards:
                dropped.append(cid)
                continue
            selected.append(cid)
            if level < depth:
                fm = parse_frontmatter((concepts_dir / f"{cid}.md").read_text())
                parent_regime = fm.get("regime")
                for rid in fm.get("related") or []:
                    if rid in seen:
                        continue
                    if not (concepts_dir / f"{rid}.md").exists():  # tolerate broken links
                        continue
                    child_regime = parse_frontmatter(
                        (concepts_dir / f"{rid}.md").read_text()).get("regime")
                    if parent_regime and child_regime and parent_regime != child_regime:
                        continue  # cross-regime auto-expansion guard — do NOT mark seen; a
                        # same-regime parent may still legitimately reach this neighbour
                    seen.add(rid)
                    next_frontier.append(rid)
        frontier = next_frontier
        level += 1
    if max_chars is not None:  # char budget; always keep at least the first card
        kept: list[str] = []
        used = 0
        for cid in selected:
            text = (concepts_dir / f"{cid}.md").read_text()
            if kept and used + len(text) > max_chars:
                dropped.append(cid)
            else:
                kept.append(cid)
                used += len(text)
        selected = kept
    bundle = "\n\n---\n\n".join((concepts_dir / f"{c}.md").read_text() for c in selected)
    return {"card_ids": selected, "bundle": bundle, "dropped": dropped}

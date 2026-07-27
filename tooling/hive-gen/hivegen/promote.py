"""Promote approved draft cards into the bundle; validate frontmatter + cross-links."""
from __future__ import annotations

from pathlib import Path

import yaml

_REQUIRED = {"type", "title", "description", "tags", "resource", "sources",
             "related", "distilled_at", "status"}


def parse_frontmatter(text: str) -> dict:
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


def validate_card(text: str, known_ids: set[str]) -> list[str]:
    fm = parse_frontmatter(text)
    errors = [f"missing frontmatter key: {k}" for k in _REQUIRED if k not in fm]
    for rid in fm.get("related", []) or []:
        if rid not in known_ids:
            errors.append(f"related id not in taxonomy: {rid}")
    return errors


def promote(drafts_dir, concepts_dir, product) -> tuple[list[str], dict[str, list[str]]]:
    drafts_dir, concepts_dir = Path(drafts_dir), Path(concepts_dir)
    known_ids = {p.relative_to(concepts_dir).with_suffix("").as_posix()
                 for p in concepts_dir.rglob("*.md")}
    known_ids |= {f"{product}/{p.stem}" for p in drafts_dir.glob("*.md")}
    promoted: list[str] = []
    invalid: dict[str, list[str]] = {}
    dest_dir = concepts_dir / product
    for p in sorted(drafts_dir.glob("*.md")):
        text = p.read_text()
        if parse_frontmatter(text).get("status") != "approved":
            continue
        dest = dest_dir / p.name
        if dest.exists():
            invalid[p.name] = [f"would overwrite existing card at {product}/{p.name}"]
            continue
        errs = validate_card(text, known_ids)
        if errs:
            invalid[p.name] = errs
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        p.unlink()
        promoted.append(p.name)
    return promoted, invalid

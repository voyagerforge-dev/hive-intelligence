"""Resolve distiller link candidates to real card ids. Unresolvable candidates are dropped.

A link is only emitted if it resolves to a card that actually exists - never invented.
"""
from __future__ import annotations

from pathlib import Path

SKIP_NAMES = {"index.md", "log.md"}


def load_card_ids(concepts_dir: str | Path) -> set[str]:
    base = Path(concepts_dir)
    return {
        p.relative_to(base).with_suffix("").as_posix()
        for p in base.rglob("*.md")
        if p.name not in SKIP_NAMES
    }


def resolve_related(candidates: list[str], card_ids: set[str]) -> list[str]:
    by_slug: dict[str, str] = {}
    for cid in card_ids:
        by_slug.setdefault(cid.rsplit("/", 1)[-1], cid)
    out: list[str] = []
    for cand in candidates or []:
        c = (cand or "").strip().strip("/")
        if not c:
            continue
        hit = c if c in card_ids else by_slug.get(c.rsplit("/", 1)[-1])
        if hit and hit not in out:
            out.append(hit)
    return sorted(out)

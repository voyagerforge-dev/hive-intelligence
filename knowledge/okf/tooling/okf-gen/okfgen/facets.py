# knowledge/okf/tooling/okf-gen/okfgen/facets.py
"""Pure facet helpers over OKF card frontmatter: read, idempotent stamp, cross-facet edge lint."""
from __future__ import annotations

import re

import yaml


def _split(card_text: str) -> tuple[str, str]:
    """Return (frontmatter_block, remainder_including_closing_fence_and_body)."""
    parts = card_text.split("---", 2)
    if len(parts) < 3:
        return "", card_text
    return parts[1], parts[2]


def read_facets(card_text: str) -> dict:
    fm, _ = _split(card_text)
    if not fm:
        return {}
    data = yaml.safe_load(fm)
    return data if isinstance(data, dict) else {}


def card_regime(card_text: str) -> str | None:
    v = read_facets(card_text).get("regime")
    return v if isinstance(v, str) else None


def stamp_facets(card_text: str, facets: dict) -> str:
    fm, body = _split(card_text)
    if not fm:
        return card_text  # no frontmatter to stamp
    present = read_facets(card_text)
    additions = "".join(
        f"{k}: {v}\n" for k, v in facets.items() if k not in present
    )
    if not additions:
        return card_text
    fm = fm.rstrip("\n") + "\n" + additions
    return f"---{fm}---{body}"


def cross_facet_edges(cards: dict[str, str], facet: str = "regime") -> list[tuple[str, str]]:
    values = {cid: read_facets(t).get(facet) for cid, t in cards.items()}
    edges: list[tuple[str, str]] = []
    for cid, text in cards.items():
        src = values.get(cid)
        for dst in read_facets(text).get("related") or []:
            if dst not in cards:
                continue
            dv = values.get(dst)
            if src is not None and dv is not None and src != dv:
                edges.append((cid, dst))
    return edges


_VERSION_RE = re.compile(r"open-systems-(20\d\d)")


def derive_versions(card_text: str) -> list[str]:
    years: set[str] = set()
    for s in read_facets(card_text).get("sources") or []:
        ref = s.get("ref", "") if isinstance(s, dict) else ""
        years.update(_VERSION_RE.findall(ref))
    return sorted(years)

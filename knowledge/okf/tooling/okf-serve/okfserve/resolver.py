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


def _client_of_id(card_id: str):
    """Client scope of a card, derived structurally from its id path (matches load_index):
    clients/<client>/... -> <client>; any other id -> None (core)."""
    if card_id.startswith("clients/"):
        parts = card_id.split("/")
        if len(parts) >= 2:
            return parts[1]
    return None


def card_path(concepts_dir, card_id, clients_dir=None):
    """Map a card id to its file. `clients/…` ids resolve under clients_dir, all others
    under concepts_dir. Returns None if the file is missing or the path escapes its base."""
    if clients_dir is not None and card_id.startswith("clients/"):
        base = Path(clients_dir).resolve()
        p = (base / f"{card_id[len('clients/'):]}.md").resolve()
    else:
        base = Path(concepts_dir).resolve()
        p = (base / f"{card_id}.md").resolve()
    if base != p and base not in p.parents:
        return None
    return p if p.exists() else None


def load_index(concepts_dir, clients_dir=None) -> list[dict]:
    concepts_dir = Path(concepts_dir)
    out: list[dict] = []
    for p in sorted(concepts_dir.rglob("*.md")):
        if p.name in ("index.md", "log.md"):
            continue
        rel = p.relative_to(concepts_dir)
        if "db" in rel.parts[:-1]:   # concepts/<product>/db/** is the on-demand db-object tier
            continue
        cid = rel.with_suffix("").as_posix()
        fm = parse_frontmatter(p.read_text())
        out.append({"id": cid, "title": fm.get("title", cid),
                    "description": fm.get("description", ""),
                    "regime": fm.get("regime"), "type": fm.get("type", "concept"),
                    "version": fm.get("version"), "product": fm.get("product"),
                    "client": None,
                    "corrects": fm.get("corrects"), "status": fm.get("status")})
    if clients_dir is not None:
        cdir = Path(clients_dir)
        if cdir.exists():
            for p in sorted(cdir.rglob("*.md")):
                if p.name in ("index.md", "log.md"):
                    continue
                rel = p.relative_to(cdir).with_suffix("")
                parts = rel.parts
                if len(parts) < 3 or parts[1] != "memory":
                    continue  # only <client>/memory/<slug>.md
                fm = parse_frontmatter(p.read_text())
                out.append({"id": "clients/" + rel.as_posix(),
                            "title": fm.get("title", rel.as_posix()),
                            "description": fm.get("description", ""),
                            "regime": fm.get("regime"), "type": "memory",
                            "version": fm.get("version"), "product": fm.get("product"),
                            "client": parts[0],
                            "corrects": fm.get("corrects"), "status": fm.get("status")})
    return out


def corrections_by_target(index: list[dict]) -> dict[str, list[str]]:
    """concept id -> active correction ids (type==correction, status==approved)."""
    out: dict[str, list[str]] = {}
    for c in index:
        if c.get("type") == "correction" and c.get("status") == "approved" and c.get("corrects"):
            out.setdefault(c["corrects"], []).append(c["id"])
    return out


def get_card(concepts_dir, card_id: str, clients_dir=None) -> str | None:
    p = card_path(concepts_dir, card_id, clients_dir)
    return p.read_text() if p is not None else None


def resolve(concepts_dir, ids: list[str], *, depth: int = 1, max_cards: int = 8,
            max_chars: int | None = None, corrections: dict[str, list[str]] | None = None,
            clients_dir=None, client=None) -> dict:
    def cpath(cid):
        return card_path(concepts_dir, cid, clients_dir)

    def cfm(cid):
        p = cpath(cid)
        return parse_frontmatter(p.read_text()) if p is not None else {}

    def in_scope(cid):
        cl = _client_of_id(cid)
        return cl is None or cl == client          # client-scoped cards only in their own scope

    selected: list[str] = []
    dropped: list[str] = []
    frontier = [i for i in ids if cpath(i) is not None and in_scope(i)]
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
                fm = cfm(cid)
                parent_regime = fm.get("regime")
                for rid in fm.get("related") or []:
                    if rid in seen:
                        continue
                    rp = cpath(rid)
                    if rp is None:  # tolerate broken links
                        continue
                    rfm = parse_frontmatter(rp.read_text())
                    if parent_regime and rfm.get("regime") and parent_regime != rfm.get("regime"):
                        continue  # cross-regime auto-expansion guard (do NOT mark seen)
                    rcl = _client_of_id(rid)
                    if rcl is not None and rcl != client:
                        continue  # cross-client / out-of-scope memory guard (do NOT mark seen)
                    seen.add(rid)
                    next_frontier.append(rid)
        frontier = next_frontier
        level += 1
    if max_chars is not None:
        kept: list[str] = []
        used = 0
        for cid in selected:
            text = cpath(cid).read_text()
            if kept and used + len(text) > max_chars:
                dropped.append(cid)
            else:
                kept.append(cid)
                used += len(text)
        selected = kept
    if corrections is None:
        corrections = corrections_by_target(load_index(concepts_dir, clients_dir))
    correction_ids: list[str] = []
    for cid in selected:
        for corr in corrections.get(cid, []):
            if corr in selected or corr in correction_ids:
                continue
            if cpath(corr) is not None:
                correction_ids.append(corr)
    all_ids = selected + correction_ids
    bundle = "\n\n---\n\n".join(cpath(c).read_text() for c in all_ids)
    return {"card_ids": all_ids, "bundle": bundle, "dropped": dropped, "corrections": correction_ids}

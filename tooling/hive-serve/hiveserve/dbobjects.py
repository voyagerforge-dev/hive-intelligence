"""LLM-free keyword search over per-product WMOS db-object manifests.

The parser (hive-dbparse) emits one manifest per product at
`concepts/<product>/db/manifest.jsonl` — one JSON object per line with
{id, kind, module, product, title, description, tags}. Task 7 excluded these
rows from the concept index (they're schema-level, not narrative cards), so
this module + the `find_db_objects` MCP tool is the only path back to them.

Matching mirrors `ledger.recall`: case-insensitive substring/token matching,
no embeddings, no network.
"""
from __future__ import annotations

import json
from pathlib import Path


def _load_rows(concepts_dir) -> list[dict]:
    rows: list[dict] = []
    for manifest in sorted(Path(concepts_dir).glob("*/db/manifest.jsonl")):
        for line in manifest.read_text().splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _score(row: dict, tokens: list[str]) -> int:
    hay = " ".join([
        row.get("title", ""),
        row.get("description", ""),
        row.get("id", ""),
        " ".join(row.get("tags", []) or []),
    ]).lower()
    return sum(1 for t in tokens if t in hay)


def search(concepts_dir, query: str, kind: str | None = None, module: str | None = None,
           limit: int = 20) -> list[dict]:
    tokens = [t for t in query.lower().split() if t]
    if not tokens:
        return []

    hits = []
    for row in _load_rows(concepts_dir):
        if kind is not None and row.get("kind") != kind:
            continue
        if module is not None and row.get("module") != module:
            continue
        score = _score(row, tokens)
        if score > 0:
            hits.append((score, row))

    hits.sort(key=lambda sr: (-sr[0], sr[1].get("id", "")))
    return [
        {
            "id": row.get("id"),
            "kind": row.get("kind"),
            "module": row.get("module"),
            "product": row.get("product"),
            "title": row.get("title"),
            "description": row.get("description"),
        }
        for _, row in hits[:limit]
    ]

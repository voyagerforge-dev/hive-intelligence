"""LLM-free keyword search over per-product database-object manifests.

The parser (hive-dbparse) emits one manifest per product at
`concepts/<product>/db/manifest.jsonl`, one JSON object per line with
{id, kind, module, product, title, description, tags}. Task 7 excluded these
rows from the concept index (they're schema-level, not narrative cards), so
this module + the `find_db_objects` MCP tool is the only path back to them.

Ranking is `ranking.rank`, shared with `find_concepts`: whole-token matching over
stopword-stripped, punctuation-free tokens, weighted by inverse document frequency. Still
no embeddings and no network.
"""
from __future__ import annotations

import json
from pathlib import Path

from hiveserve.ranking import rank


def _load_rows(concepts_dir) -> list[dict]:
    rows: list[dict] = []
    for manifest in sorted(Path(concepts_dir).glob("*/db/manifest.jsonl")):
        for line in manifest.read_text().splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _text(row: dict) -> str:
    return " ".join([
        row.get("title", ""),
        row.get("description", ""),
        row.get("id", ""),
        " ".join(row.get("tags", []) or []),
    ])


def search(concepts_dir, query: str, kind: str | None = None, module: str | None = None,
           limit: int = 20) -> list[dict]:
    candidates = [
        row for row in _load_rows(concepts_dir)
        if (kind is None or row.get("kind") == kind)
        and (module is None or row.get("module") == module)
    ]
    hits = rank(query, ((row, _text(row)) for row in candidates), limit,
                lambda row: row.get("id", ""))
    return [
        {
            "id": row.get("id"),
            "kind": row.get("kind"),
            "module": row.get("module"),
            "product": row.get("product"),
            "title": row.get("title"),
            "description": row.get("description"),
        }
        for row in hits
    ]

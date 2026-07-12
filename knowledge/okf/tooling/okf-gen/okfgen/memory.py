"""Pure record⇄card serialization seam for OKF client-memory cards.
A `record` is a surface-agnostic dict; a memory card is conformant markdown at
clients/<client>/memory/<slug>.md. new_memory.py (CLI) and the memory-from-issue
Action both author cards through record_to_memory."""
from __future__ import annotations

import re

import yaml


def record_to_memory(record: dict) -> str:
    fm = {
        "type": "memory",
        "title": record["title"],
        "description": record.get("description", ""),
        "client": record["client"],
        "product": record["product"],
        "platform": record.get("platform", ""),
        "related": record.get("related", []),
        "supersedes": record.get("supersedes", []),
        "tags": record.get("tags", []),
        "submitted_by": record.get("submitted_by", ""),
        "resource": record.get("resource", ""),
        "sources": [{"kind": "memory-source", "ref": r}
                    for r in record.get("citations", [])],
        "timestamp": record.get("timestamp", ""),
        "status": record.get("status", "approved"),
    }
    fm_text = yaml.safe_dump(fm, sort_keys=False,
                             allow_unicode=True).rstrip("\n")
    body = (f"## Memory\n\n{record['memory'].rstrip()}\n\n"
            f"## Context\n\n{record.get('context', '').rstrip()}\n")
    return f"---\n{fm_text}\n---\n\n{body}"


def _section(body: str, heading: str) -> str:
    m = re.search(rf"(?ms)^{re.escape(heading)}\s*\n(.*?)(?=\n#|\Z)",
                  body)
    return m.group(1).strip() if m else ""


_FRONTMATTER_RE = re.compile(r"(?s)^---\s*\n(.*?)\n---\s*\n?(.*)$")


def memory_to_record(card_text: str) -> dict:
    m = _FRONTMATTER_RE.match(card_text)
    if not m:
        fm: dict = {}
        body = ""
    else:
        fm = yaml.safe_load(m.group(1)) or {}
        body = m.group(2)
    return {
        "client": fm.get("client", ""),
        "product": fm.get("product", ""),
        "title": fm.get("title", ""),
        "description": fm.get("description", ""),
        "memory": _section(body, "## Memory"),
        "context": _section(body, "## Context"),
        "platform": fm.get("platform", ""),
        "related": fm.get("related", []),
        "tags": fm.get("tags", []),
        "citations": [s.get("ref") for s in (fm.get("sources") or [])
                      if isinstance(s, dict)],
        "supersedes": fm.get("supersedes", []),
        "submitted_by": fm.get("submitted_by", ""),
        "status": fm.get("status", "approved"),
        "timestamp": fm.get("timestamp", ""),
    }

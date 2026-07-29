"""Scaffold a memory card under clients/<client>/memory/. Fill it in, then PR.
Usage: python scripts/new_memory.py <client> <product> "<title>" [clients_dir]"""
import re
import sys
from pathlib import Path

from hivegen.memory import record_to_memory


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def build(client: str, product: str, title: str, *, out_dir, timestamp: str) -> Path:
    record = {
        "client": client, "product": product, "title": title, "description": "",
        "memory": "<state the client-specific operational fact here>",
        "context": "<when it applies / the modification scope>",
        "platform": "", "related": [], "tags": [], "citations": [], "supersedes": [],
        "submitted_by": "", "status": "draft", "timestamp": timestamp,
    }
    d = Path(out_dir) / client / "memory"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{_slug(title)}.md"
    p.write_text(record_to_memory(record))
    return p


if __name__ == "__main__":  # pragma: no cover
    from datetime import UTC, datetime
    client, product, title = sys.argv[1], sys.argv[2], sys.argv[3]
    clients = sys.argv[4] if len(sys.argv) > 4 else "clients"
    out = build(client, product, title, out_dir=clients, timestamp=datetime.now(UTC).date().isoformat())
    print(f"scaffolded {out} (fill in Memory/Context, set status: approved, then PR)")

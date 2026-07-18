"""Per-client, per-org incremental cursor.

Not a naive high-water mark: the stored bound is pushed back below the oldest
still-unprocessed ticket so a partial failure is re-pulled next run. The connector's
`since` is strictly greater-than, and already-emitted cards are skipped, so replaying a
window is cheap and safe.
"""
from __future__ import annotations

import json
from pathlib import Path

EPOCH = "1970-01-01T00:00:00Z"


def _path(state_dir: str | Path, client: str) -> Path:
    return Path(state_dir) / f"{client}.json"


def load_state(state_dir: str | Path, client: str) -> dict[str, str]:
    p = _path(state_dir, client)
    if not p.exists():
        return {}
    return json.loads(p.read_text() or "{}")


def save_state(state_dir: str | Path, client: str, per_org: dict[str, str]) -> Path:
    p = _path(state_dir, client)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(per_org, indent=2, sort_keys=True) + "\n")
    return p


def replay_since(stored_since: str | None, oldest_unprocessed: str | None) -> str:
    if oldest_unprocessed:
        return oldest_unprocessed
    return stored_since or EPOCH

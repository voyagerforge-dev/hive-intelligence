"""Content-SHA duplicate grouping, provable byte-identical dupes for the curator."""
from __future__ import annotations
import hashlib
from pathlib import Path

def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()

def group_duplicates(paths: list[Path]) -> dict[str, list[str]]:
    """Group paths by content SHA-256; return only groups with >1 member."""
    groups: dict[str, list[str]] = {}
    for p in paths:
        groups.setdefault(sha256_file(p), []).append(str(p))
    return {sha: sorted(ps) for sha, ps in groups.items() if len(ps) > 1}

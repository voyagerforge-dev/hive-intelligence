# knowledge/okf/tooling/okf-gen/scripts/osci_facet_apply.py
"""Stamp oSCI facets (product/platform/version) on promoted cards, deterministically.
version = union of each card's source docs' folder-year (`version:` in the atomic md
frontmatter). product/platform are uniform. No LLM/gate. Mirrors version_apply.py.
Usage: python scripts/osci_facet_apply.py <concepts_dir> <atomic_dir>"""
import glob
import os
import sys
from pathlib import Path

import yaml

from okfgen.facets import read_facets, stamp_facets


def _atomic_version(atomic_dir: Path, ref: str) -> list[str]:
    p = atomic_dir / ref
    if not p.exists():
        return []
    v = read_facets(p.read_text()).get("version")
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [str(x) for x in v]
    return []


def versions_for_card(card_text: str, atomic_dir) -> list[str]:
    atomic_dir = Path(atomic_dir)
    seen: set[str] = set()
    for s in read_facets(card_text).get("sources") or []:
        ref = s.get("ref") if isinstance(s, dict) else None
        if ref:
            seen.update(_atomic_version(atomic_dir, ref))
    return sorted(seen)


def apply(concepts_dir: str, atomic_dir: str) -> None:
    n = 0
    for p in sorted(glob.glob(f"{concepts_dir}/*.md")):
        if os.path.basename(p) == "index.md":
            continue
        text = open(p).read()
        facets = {"product": "osci", "platform": "open-systems"}
        versions = versions_for_card(text, atomic_dir)
        if versions:
            facets["version"] = versions
        open(p, "w").write(stamp_facets(text, facets))
        n += 1
    print(f"stamped oSCI facets on {n} cards")


if __name__ == "__main__":
    apply(sys.argv[1], sys.argv[2])

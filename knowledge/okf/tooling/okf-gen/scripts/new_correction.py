"""Scaffold a correction card under concepts/<product>/corrections/. Fill it in, then PR.
Usage: python scripts/new_correction.py <product> <target-concept-id> "<title>" [concepts_dir]"""
import re
import sys
from pathlib import Path

from okfgen.corrections import record_to_correction


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def build(product: str, target_id: str, title: str, *, out_dir, timestamp: str) -> Path:
    record = {
        "corrects": target_id, "title": title, "description": "",
        "correction": "<state the corrected fact here>",
        "rationale": "<why — cite the source doc/section>",
        "citations": [], "supersedes": [], "product": product,
        "status": "draft", "timestamp": timestamp,
    }
    d = Path(out_dir) / product / "corrections"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{_slug(title)}.md"
    p.write_text(record_to_correction(record))
    return p


if __name__ == "__main__":  # pragma: no cover
    from datetime import date
    product, target_id, title = sys.argv[1], sys.argv[2], sys.argv[3]
    concepts = sys.argv[4] if len(sys.argv) > 4 else "concepts"
    out = build(product, target_id, title, out_dir=concepts, timestamp=date.today().isoformat())
    print(f"scaffolded {out} (fill in Correction/Rationale/citations, set status: approved, then PR)")

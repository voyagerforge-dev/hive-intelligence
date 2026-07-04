# knowledge/okf/tooling/okf-gen/scripts/regime_apply.py
"""Apply an approved regime-classification.yaml to the corpus: stamp regime on labelled cards +
uniform product/platform on all cards, then report any remaining cross-regime `related` edges.
Usage: python scripts/regime_apply.py <concepts_dir> <regime-classification.yaml>"""
import sys
from pathlib import Path

import yaml

from okfgen.facets import cross_facet_edges, stamp_facets


def main(concepts_dir: str, class_path: str) -> None:
    cdir = Path(concepts_dir)
    labels = {r["id"]: r["label"] for r in yaml.safe_load(Path(class_path).read_text())}
    for p in sorted(cdir.glob("*.md")):
        if p.name == "index.md":
            continue
        text = p.read_text()
        facets = {"product": "wms", "platform": "wmos"}      # uniform stamp
        label = labels.get(p.stem)
        if label in ("ops", "traditional"):
            facets["regime"] = label                          # regime only for participants
        p.write_text(stamp_facets(text, facets))
    cards = {p.stem: p.read_text() for p in cdir.glob("*.md") if p.name != "index.md"}
    bad = cross_facet_edges(cards, facet="regime")
    print(f"stamped {len(cards)} cards. cross-regime related edges remaining: {len(bad)}")
    for src, dst in bad:
        print(f"  FIX: {src} -> {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

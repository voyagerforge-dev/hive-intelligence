"""Apply an approved regime-classification.yaml to the corpus: stamp regime on labelled cards +
uniform product/platform on all cards, then report any remaining cross-regime `related` edges.
The uniform product/platform values are corpus vocabulary, so they are arguments rather
than constants: stamping every card with one corpus's product would misfile the lot.

Usage: python scripts/regime_apply.py <concepts_dir> <regime-classification.yaml> \
           <product> <platform>"""
import sys
from pathlib import Path

import yaml

from hivegen.facets import cross_facet_edges, stamp_facets


def main(concepts_dir: str, class_path: str, product: str, platform: str) -> None:
    cdir = Path(concepts_dir)
    labels = {r["id"]: r["label"] for r in yaml.safe_load(Path(class_path).read_text())}
    for p in sorted(cdir.glob("*.md")):
        if p.name == "index.md":
            continue
        text = p.read_text()
        facets = {"product": product, "platform": platform}   # uniform stamp
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
    if len(sys.argv) != 5:
        raise SystemExit(
            "usage: regime_apply.py <concepts_dir> <regime-classification.yaml> "
            "<product> <platform>\n"
            "  product and platform are stamped uniformly on every card, so they must be "
            "this corpus's values rather than a default.")
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])

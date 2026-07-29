"""Regenerate the OKF index hierarchy for the concepts bundle (progressive disclosure).
  - root index.md: `okf_version: "0.1"` frontmatter (the one place frontmatter is allowed
    in an index) + a section linking to each product's index with a concept count.
  - <product>/index.md: no frontmatter, a section per product listing its concepts as
    bundle-relative markdown links with descriptions.
Reserved-file rule: index.md is skipped by the card loader at any level.
Usage: python scripts/index_generate.py <concepts_dir>
"""
import glob
import os
import sys

import yaml

from hivegen.profile import load_profile

# Display titles for product facets. Corpus vocabulary, so it comes from the profile; a
# product with no declared title falls back to its facet value, which reads acceptably.
PRODUCT_NAMES = load_profile().product_titles


def _cards_by_product(concepts_dir):
    out = {}
    for p in sorted(glob.glob(f"{concepts_dir}/*/*.md")):
        if os.path.basename(p) in ("index.md", "log.md"):
            continue
        product = os.path.relpath(p, concepts_dir).split("/", 1)[0]
        cid = os.path.relpath(p, concepts_dir)[:-3]
        with open(p) as _fh:
            _text = _fh.read()
        fm = yaml.safe_load(_text.split("---", 2)[1]) or {}
        if fm.get("type") == "correction":
            continue
        out.setdefault(product, []).append(
            (cid, fm.get("title", cid), fm.get("description", "")))
    return out


def generate(concepts_dir):
    by_product = _cards_by_product(concepts_dir)
    total = sum(len(v) for v in by_product.values())
    # per-product index files
    for product, cards in by_product.items():
        name = PRODUCT_NAMES.get(product, product)
        lines = [f"# {name}", "",
                 f"{len(cards)} concepts.", ""]
        for cid, title, desc in sorted(cards, key=lambda c: c[1].lower()):
            suffix = f", {desc}" if desc else ""
            lines.append(f"- [{title}](/{cid}.md){suffix}")
        with open(f"{concepts_dir}/{product}/index.md", "w") as _fh:
            _fh.write("\n".join(lines) + "\n")
    # root index
    root = ['---', 'okf_version: "0.1"', '---', "",
            "# Knowledge Bundle Index", "",
            (f"Curated OKF knowledge, organised by product. {total} concepts across "
            f"{len(by_product)} products."), "",
            "## Products", ""]
    for product in sorted(by_product, key=lambda k: -len(by_product[k])):
        name = PRODUCT_NAMES.get(product, product)
        root.append(f"- [{name}](/{product}/index.md), {len(by_product[product])} concepts")
    with open(f"{concepts_dir}/index.md", "w") as _fh:
        _fh.write("\n".join(root) + "\n")
    print(f"wrote root index + {len(by_product)} product indexes ({total} concepts)")


if __name__ == "__main__":
    generate(sys.argv[1])

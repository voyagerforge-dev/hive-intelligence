# knowledge/okf/tooling/okf-gen/scripts/version_apply.py
"""Stamp the `version` facet on cards from their source-ref release years (deterministic,
no LLM/gate). Version-neutral cards (no year in sources) are left untouched.
Usage: python scripts/version_apply.py <concepts_dir>"""
import collections
import glob
import os
import sys

from okfgen.facets import derive_versions, stamp_facets


def main(concepts_dir: str) -> None:
    dist = collections.Counter()
    for p in sorted(glob.glob(f"{concepts_dir}/*.md")):
        if os.path.basename(p) == "index.md":
            continue
        text = open(p).read()
        versions = derive_versions(text)
        if versions:
            open(p, "w").write(stamp_facets(text, {"version": versions}))
        dist[len(versions)] += 1
    print(f"version stamps by count: {dict(sorted(dist.items()))} "
          f"(0=neutral/untouched, 1=single, 2+=multi-release)")


if __name__ == "__main__":
    main(sys.argv[1])

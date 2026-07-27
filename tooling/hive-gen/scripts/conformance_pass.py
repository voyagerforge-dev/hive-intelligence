"""One-time OKF-conformance pass over the concepts bundle (idempotent).
For every concept card:
  - frontmatter: set `resource` to the served-card URI; add `timestamp` (from distilled_at).
  - body: append a `## Related` section with bundle-relative markdown links (from the
    `related` frontmatter) and a `# Citations` section (from the `sources` frontmatter),
    so relationships and citations are expressed in OKF-idiomatic body markdown, not only
    in custom frontmatter. Existing frontmatter keys are preserved.
Usage: python scripts/conformance_pass.py <concepts_dir>
"""
import glob
import os
import re
import sys

import yaml

# Per-deployment: the public base a card id resolves under. Cards are portable, so this
# cannot be baked in. Set CARD_BASE_URL in the environment of whoever runs the pass.
BASE_URL = os.environ.get("CARD_BASE_URL", "https://hive.example.com/card")


def _title_map(concepts_dir):
    m = {}
    for p in glob.glob(f"{concepts_dir}/**/*.md", recursive=True):
        if os.path.basename(p) in ("index.md", "log.md"):
            continue
        cid = os.path.relpath(p, concepts_dir)[:-3]
        fm = yaml.safe_load(open(p).read().split("---", 2)[1]) or {}
        m[cid] = fm.get("title", cid)
    return m


def _edit_frontmatter(fm_text, cid, timestamp):
    """Targeted line edits: set resource to the served URI; add timestamp after distilled_at."""
    lines = fm_text.split("\n")
    out = []
    has_ts = any(re.match(r"^timestamp:", ln) for ln in lines)
    for ln in lines:
        if re.match(r"^resource:", ln):
            out.append(f"resource: {BASE_URL}/{cid}")
            continue
        out.append(ln)
        if not has_ts and re.match(r"^distilled_at:", ln) and timestamp:
            out.append(f"timestamp: '{timestamp}'")
    return "\n".join(out)


def _related_section(related, titles):
    rows = []
    for rid in related or []:
        if rid in titles:
            rows.append(f"- [{titles[rid]}](/{rid}.md)")
    return ("## Related\n\n" + "\n".join(rows) + "\n") if rows else ""


def _citations_section(sources):
    refs = [s.get("ref") for s in (sources or []) if isinstance(s, dict) and s.get("ref")]
    if not refs:
        return ""
    body = "\n".join(f"{i}. `{r}`" for i, r in enumerate(refs, 1))
    return "# Citations\n\n" + body + "\n"


def _strip_generated(body):
    # strip any existing ## Related (stop at next h1/h2) and # Citations (stop at next h1) block
    body = re.sub(r"\n*## Related\b.*?(?=\n#{1,2} |\Z)", "", body, flags=re.S)
    body = re.sub(r"\n*# Citations\b.*?(?=\n# |\Z)", "", body, flags=re.S)
    return body.rstrip("\n")


def process(concepts_dir):
    titles = _title_map(concepts_dir)
    n = rel = cit = 0
    for p in sorted(glob.glob(f"{concepts_dir}/**/*.md", recursive=True)):
        if os.path.basename(p) in ("index.md", "log.md"):
            continue
        cid = os.path.relpath(p, concepts_dir)[:-3]
        text = open(p).read()
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        fm = yaml.safe_load(parts[1]) or {}
        new_fm = _edit_frontmatter(parts[1], cid, fm.get("distilled_at"))
        body = _strip_generated(parts[2])  # remove any prior generated sections
        add = ""
        rs = _related_section(fm.get("related"), titles)
        if rs:
            add += "\n\n" + rs.rstrip("\n")
            rel += 1
        cs = _citations_section(fm.get("sources"))
        if cs:
            add += "\n\n" + cs.rstrip("\n")
            cit += 1
        open(p, "w").write(f"---{new_fm}---{body}{add}\n")
        n += 1
    print(f"processed {n} cards | Related sections {rel} | Citations sections {cit}")


if __name__ == "__main__":
    process(sys.argv[1])

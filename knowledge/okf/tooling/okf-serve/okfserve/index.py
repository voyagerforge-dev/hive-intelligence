"""OKF format pass: emit index.md (progressive-disclosure entry point) and
render `related` frontmatter into spec-native inline markdown cross-links."""
from __future__ import annotations

import re
from pathlib import Path

from okfserve.resolver import load_index, parse_frontmatter

_MARK = "## Related"
# Match ONLY our own exact "## Related" section (a heading line equal to
# "## Related"), never a differently-named heading like "## Related References"
# that may legitimately exist in a distilled card body.
_OUR_SECTION = re.compile(r"\n## Related\n.*\Z", re.DOTALL)


def build_index_md(concepts_dir) -> str:
    lines = ["# Index", ""]
    for c in load_index(concepts_dir):
        tag = f" _(regime: {c['regime']})_" if c.get("regime") else ""
        lines.append(f"- [{c['title']}](./{c['id']}.md){tag} — {c['description']}")
    return "\n".join(lines) + "\n"


def render_crosslinks(card_text: str, titles: dict[str, str]) -> str:
    body = _OUR_SECTION.sub("", card_text).rstrip()  # drop only our prior section
    fm = parse_frontmatter(card_text)
    related = fm.get("related") or []
    if not related:
        return body + "\n"
    links = [f"- [{titles.get(rid, rid)}](./{rid}.md)" for rid in related]
    return body + f"\n\n{_MARK}\n\n" + "\n".join(links) + "\n"


def apply_format_pass(concepts_dir) -> dict:
    concepts_dir = Path(concepts_dir)
    titles = {c["id"]: c["title"] for c in load_index(concepts_dir)}
    (concepts_dir / "index.md").write_text(build_index_md(concepts_dir))
    updated: list[str] = []
    for p in sorted(concepts_dir.glob("*.md")):
        if p.name == "index.md":
            continue
        before = p.read_text()
        after = render_crosslinks(before, titles)
        if after != before:
            p.write_text(after)
            updated.append(p.stem)
    return {"index": "index.md", "updated": updated}

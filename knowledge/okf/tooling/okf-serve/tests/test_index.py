from okfserve.index import apply_format_pass, build_index_md, render_crosslinks

CARD = """---
title: Alpha
description: the alpha card
related:
- beta
status: approved
---

Alpha body.
"""

BETA = """---
title: Beta
description: beta
related: []
status: approved
---

Beta body.
"""


def test_build_index_md(tmp_path):
    (tmp_path / "alpha.md").write_text(CARD)
    (tmp_path / "beta.md").write_text(BETA)
    md = build_index_md(tmp_path)
    assert md.startswith("# Index")
    assert "- [Alpha](./alpha.md) — the alpha card" in md
    assert "- [Beta](./beta.md) — beta" in md


def test_render_crosslinks_adds_related_section():
    out = render_crosslinks(CARD, {"beta": "Beta"})
    assert "## Related" in out
    assert "- [Beta](./beta.md)" in out
    assert out.rstrip().endswith("- [Beta](./beta.md)")


def test_render_crosslinks_idempotent():
    once = render_crosslinks(CARD, {"beta": "Beta"})
    twice = render_crosslinks(once, {"beta": "Beta"})
    assert once == twice


def test_apply_format_pass_writes_index_and_links(tmp_path):
    (tmp_path / "alpha.md").write_text(CARD)
    (tmp_path / "beta.md").write_text(BETA)
    res = apply_format_pass(tmp_path)
    assert (tmp_path / "index.md").exists()
    assert "alpha" in res["updated"]
    assert "## Related" in (tmp_path / "alpha.md").read_text()

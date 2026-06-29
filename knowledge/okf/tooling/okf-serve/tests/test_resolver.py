from okfserve.resolver import get_card, load_index, parse_frontmatter, resolve

CARD_A = """---
title: Alpha
description: the alpha card
related:
- beta
- ghost
sources:
- kind: wms-doc
  ref: a.md
status: approved
---

Alpha body.
"""

CARD_B = """---
title: Beta
description: the beta card
related:
- gamma
sources: []
status: approved
---

Beta body.
"""

CARD_G = """---
title: Gamma
description: the gamma card
related: []
sources: []
status: approved
---

Gamma body.
"""


def _write(tmp_path):
    (tmp_path / "alpha.md").write_text(CARD_A)
    (tmp_path / "beta.md").write_text(CARD_B)
    (tmp_path / "gamma.md").write_text(CARD_G)
    return tmp_path


def test_parse_frontmatter():
    fm = parse_frontmatter(CARD_A)
    assert fm["title"] == "Alpha"
    assert fm["related"] == ["beta", "ghost"]


def test_load_index_sorted(tmp_path):
    _write(tmp_path)
    idx = load_index(tmp_path)
    assert [c["id"] for c in idx] == ["alpha", "beta", "gamma"]
    assert idx[0]["description"] == "the alpha card"


def test_get_card_present_and_absent(tmp_path):
    _write(tmp_path)
    assert "Alpha body." in get_card(tmp_path, "alpha")
    assert get_card(tmp_path, "nope") is None


def test_resolve_follows_related_to_depth_and_tolerates_broken(tmp_path):
    _write(tmp_path)
    out = resolve(tmp_path, ["alpha"], depth=1, max_cards=8)
    # depth 1 from alpha -> beta (ghost is broken, skipped); gamma is depth 2, excluded
    assert out["card_ids"] == ["alpha", "beta"]
    assert "ghost" not in out["card_ids"]
    assert "Alpha body." in out["bundle"] and "Beta body." in out["bundle"]


def test_resolve_depth_two_reaches_gamma(tmp_path):
    _write(tmp_path)
    out = resolve(tmp_path, ["alpha"], depth=2, max_cards=8)
    assert out["card_ids"] == ["alpha", "beta", "gamma"]


def test_resolve_caps_and_records_dropped(tmp_path):
    _write(tmp_path)
    out = resolve(tmp_path, ["alpha"], depth=2, max_cards=2)
    assert out["card_ids"] == ["alpha", "beta"]
    assert out["dropped"] == ["gamma"]

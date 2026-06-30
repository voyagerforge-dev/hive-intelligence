from okfserve import tools

CARD = """---
title: Wave Replen
description: how replen feeds waves
related: []
sources: [wms.md]
---
Body text.
"""


def _seed(tmp_path):
    (tmp_path / "wave-replen.md").write_text(CARD)
    return tmp_path


def test_list_concepts(tmp_path):
    d = _seed(tmp_path)
    idx = tools.list_concepts(d)
    assert idx == [{"id": "wave-replen", "title": "Wave Replen",
                    "description": "how replen feeds waves"}]


def test_get_card_text_present_and_missing(tmp_path):
    d = _seed(tmp_path)
    assert "Body text." in tools.get_card_text(d, "wave-replen")
    assert "No card" in tools.get_card_text(d, "nope")


def test_resolve_cards(tmp_path):
    d = _seed(tmp_path)
    out = tools.resolve_cards(d, ["wave-replen"], depth=1)
    assert out["card_ids"] == ["wave-replen"]
    assert "Body text." in out["bundle"]

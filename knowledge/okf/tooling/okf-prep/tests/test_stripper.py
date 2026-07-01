from okfprep.stripper import load_stripping_rules, strip_boilerplate

_DOC = """# Replenishment Logic

Manhattan Associates — Confidential
Copyright 2013 Manhattan Associates, Inc. All Rights Reserved.

WM triggers replenishment when the on-hand quantity falls below a minimum.

SCALE is a registered trademark of Manhattan Associates.
Page 3 of 42
"""


def test_wmos_strips_boilerplate_keeps_content():
    r = strip_boilerplate(_DOC, product="wmos")
    # boilerplate gone
    assert "Manhattan Associates" not in r.text
    assert "Confidential" not in r.text
    assert "Copyright" not in r.text
    assert "All Rights Reserved" not in r.text
    assert "registered trademark" not in r.text
    assert "Page 3 of 42" not in r.text
    # real content kept
    assert "WM triggers replenishment" in r.text
    assert "# Replenishment Logic" in r.text
    assert r.regex_matches > 0
    assert r.stripped_length < r.original_length


def test_unknown_product_falls_back_to_default():
    # default.yaml still strips generic copyright + page footers
    doc = "Real text.\nCopyright 2020 Acme Corp.\nPage 1 of 9\n"
    r = strip_boilerplate(doc, product="does-not-exist")
    assert "Copyright" not in r.text and "Page 1 of 9" not in r.text
    assert "Real text." in r.text


def test_disabled_style_noop_via_load():
    # load returns compiled patterns; sanity that rules load and compile
    pats = load_stripping_rules("wmos")
    assert len(pats) >= 5

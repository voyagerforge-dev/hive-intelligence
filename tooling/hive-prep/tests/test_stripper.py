from hiveprep.stripper import load_stripping_rules, strip_boilerplate

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


def test_wmos_keeps_real_prose_starting_with_trigger_words():
    # Regression: the corpus IS Manhattan docs, so line-start "Manhattan Associates"/"Confidential"
    # must NOT delete legitimate prose — only footer/header FORMS are boilerplate.
    prose = (
        "Manhattan Associates WMOS supports wave templates that group orders by carrier.\n"
        "Confidential data such as customer PII must be masked in exported reports.\n"
    )
    r = strip_boilerplate(prose, product="wmos")
    assert "wave templates that group orders by carrier" in r.text
    assert "customer PII must be masked in exported reports" in r.text
    assert r.regex_matches == 0  # nothing matched — both are real content


def test_wmos_still_strips_footer_forms():
    footers = (
        "Body.\n"
        "Manhattan Associates, Inc.\n"           # bare vendor footer
        "Manhattan Associates | Confidential and Proprietary\n"  # vendor + legal
        "Confidential and Proprietary Information\n"             # confidentiality footer
        "Confidentiality Notice: do not distribute.\n"
        "More body.\n"
    )
    r = strip_boilerplate(footers, product="wmos")
    assert "Manhattan Associates" not in r.text
    assert "Confidential" not in r.text
    assert "Body." in r.text and "More body." in r.text


def test_unknown_product_falls_back_to_default():
    # default.yaml still strips generic copyright + page footers
    doc = "Real text.\nCopyright 2020 Acme Corp.\nPage 1 of 9\n"
    r = strip_boilerplate(doc, product="does-not-exist")
    assert "Copyright" not in r.text and "Page 1 of 9" not in r.text
    assert "Real text." in r.text


def test_rules_load_and_compile():
    pats = load_stripping_rules("wmos")
    assert len(pats) >= 5

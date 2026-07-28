"""Boilerplate stripping.

These tests exercise the rules *engine* against a synthetic vendor, not against any real
vendor's documentation. That is deliberate. A rule set tuned to one vendor's footers is
corpus-specific and ships with the corpus; what the product owns is the mechanism, and the
mechanism is what has to keep working.

The interesting property is not "boilerplate is removed". It is that removal is anchored to
footer and header *form*, so a rule set can be aimed at a vendor whose name also appears
throughout the legitimate prose of that vendor's own manuals, without eating the prose.

Note the double backslashes below. These are YAML double-quoted scalars, where a lone ``\\s``
is an invalid escape and fails to parse. The shipped rule files escape them the same way.
"""
import textwrap

import pytest

from hiveprep.stripper import load_stripping_rules, strip_boilerplate

# A stand-in vendor whose name appears in real sentences as well as in footers, which is the
# situation every real vendor corpus is in.
_RULES = textwrap.dedent(r"""
    product: acme
    patterns:
      - type: regex
        pattern: "^\\s*Acme Corporation\\s*,?\\s*Inc\\.?\\s*(All Rights Reserved\\.?)?\\s*$"
        flags: MULTILINE
      - type: regex
        pattern: "^\\s*Acme Corporation\\s*[|-]\\s*Confidential.*$"
        flags: MULTILINE
      - type: regex
        pattern: "^\\s*Confidential and Proprietary.*$"
        flags: MULTILINE
      - type: regex
        pattern: "^\\s*Confidentiality Notice:.*$"
        flags: MULTILINE
      - type: regex
        pattern: "^\\s*(©|\\(c\\)|Copyright).*\\d{4}.*$"
        flags: "MULTILINE IGNORECASE"
      - type: regex
        pattern: "^\\s*\\w+ is a registered trademark of Acme Corporation\\.\\s*$"
        flags: MULTILINE
""").strip()

_DEFAULT_RULES = textwrap.dedent(r"""
    product: default
    patterns:
      - type: regex
        pattern: "^\\s*(©|\\(c\\)|Copyright).*\\d{4}.*$"
        flags: "MULTILINE IGNORECASE"
      - type: regex
        pattern: "^\\s*All Rights Reserved.*$"
        flags: "MULTILINE IGNORECASE"
      - type: regex
        pattern: "^\\s*Page \\d+ of \\d+\\s*$"
        flags: MULTILINE
""").strip()


@pytest.fixture
def rules_dir(tmp_path):
    d = tmp_path / "stripper_rules"
    d.mkdir()
    (d / "acme.yaml").write_text(_RULES)
    # The generic set has to be present: unknown products fall back to it.
    (d / "default.yaml").write_text(_DEFAULT_RULES)
    return d


_DOC = """# Replenishment Logic

Acme Corporation | Confidential
Copyright 2013 Acme Corporation, Inc. All Rights Reserved.

The system triggers replenishment when on-hand quantity falls below a minimum.

Widget is a registered trademark of Acme Corporation.
Page 3 of 42
"""


def test_strips_boilerplate_and_keeps_content(rules_dir):
    r = strip_boilerplate(_DOC, product="acme", rules_dir=rules_dir)
    assert "Confidential" not in r.text
    assert "Copyright" not in r.text
    assert "registered trademark" not in r.text
    assert "The system triggers replenishment" in r.text
    assert "# Replenishment Logic" in r.text
    assert r.regex_matches > 0
    assert r.stripped_length < r.original_length


def test_keeps_real_prose_that_starts_with_a_trigger_word(rules_dir):
    """The regression that matters. A corpus of a vendor's manuals is full of sentences
    beginning with that vendor's name, so matching the name alone would delete content."""
    prose = (
        "Acme Corporation supports wave templates that group orders by carrier.\n"
        "Confidential data such as customer PII must be masked in exported reports.\n"
    )
    r = strip_boilerplate(prose, product="acme", rules_dir=rules_dir)
    assert "wave templates that group orders by carrier" in r.text
    assert "customer PII must be masked in exported reports" in r.text
    assert r.regex_matches == 0


def test_still_strips_footer_forms(rules_dir):
    footers = (
        "Body.\n"
        "Acme Corporation, Inc.\n"
        "Acme Corporation | Confidential and Proprietary\n"
        "Confidential and Proprietary Information\n"
        "Confidentiality Notice: do not distribute.\n"
        "More body.\n"
    )
    r = strip_boilerplate(footers, product="acme", rules_dir=rules_dir)
    assert "Acme Corporation" not in r.text
    assert "Confidential" not in r.text
    assert "Body." in r.text and "More body." in r.text


def test_unknown_product_falls_back_to_the_generic_rules(rules_dir):
    doc = "Real text.\nCopyright 2020 Acme Corp.\nPage 1 of 9\n"
    r = strip_boilerplate(doc, product="does-not-exist", rules_dir=rules_dir)
    assert "Copyright" not in r.text and "Page 1 of 9" not in r.text
    assert "Real text." in r.text


def test_the_shipped_default_rules_load_and_compile():
    """The product ships exactly one rule set, the generic one. Vendor rule sets are
    corpus-side and are supplied by the deployment."""
    assert len(load_stripping_rules("default")) >= 2

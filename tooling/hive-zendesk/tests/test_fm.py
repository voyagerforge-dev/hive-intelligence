"""A `---` inside a value must not be mistaken for the frontmatter delimiter."""
from hivezendesk.fm import parse_frontmatter, split_frontmatter

TRICKY = """---
type: issue
title: EXAMPLE DC OLPN 0000000000 --- [#SR-000000] [Open] - a label printed
client: beta
related: []
---

## What happened

Something happened.
"""


def test_parses_frontmatter_whose_title_contains_the_delimiter():
    fm = parse_frontmatter(TRICKY)
    assert fm["client"] == "beta"          # the field a naive split loses
    assert fm["title"].startswith("EXAMPLE DC OLPN 0000000000 ---")


def test_body_is_everything_after_the_closing_delimiter():
    _, body = split_frontmatter(TRICKY)
    assert body.startswith("\n## What happened")


def test_missing_frontmatter_is_not_an_exception():
    assert parse_frontmatter("no frontmatter here") == {}
    assert split_frontmatter("no frontmatter here") is None


def test_unparsable_yaml_is_not_an_exception():
    assert parse_frontmatter("---\n: : :\n---\n") == {}

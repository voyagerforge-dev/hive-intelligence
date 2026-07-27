"""Frontmatter parsing that survives `---` appearing inside a value.

An illustrative ticket subject is `EXAMPLE DC OLPN 0000000000 --- [#SR-000000] ...`. Splitting on
the bare string `---` truncates that card's frontmatter mid-title, which made `verify_card`
reject a perfectly good card as "missing required frontmatter" - a false positive that
aborts the whole run, and does so *after* the card has been written to disk.

The delimiter is only a delimiter on a line of its own, so that is what we match.
"""
from __future__ import annotations

import re

import yaml

_FM = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def split_frontmatter(text: str) -> tuple[str, str] | None:
    """(frontmatter_yaml, body) or None when the text has no frontmatter block."""
    m = _FM.match(text or "")
    if not m:
        return None
    return m.group(1), text[m.end():]


def parse_frontmatter(text: str) -> dict:
    """Frontmatter as a dict. Returns {} when absent or unparsable."""
    parts = split_frontmatter(text)
    if not parts:
        return {}
    try:
        data = yaml.safe_load(parts[0])
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}

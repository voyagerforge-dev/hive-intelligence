import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "memory_from_issue", Path(__file__).resolve().parents[1] / "scripts" / "memory_from_issue.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)
parse_issue = mod.parse_issue
validate_record = mod.validate_record
_slug = mod._slug

BODY = """### Client

alpha

### Product

widgets

### Title

Second scan at allocation confirm

### The lesson (de-personalised)

Alpha requires a second verification scan before committing the pick.

### When it applies

Alpha site only.

### Platform (optional)

bench

### Related concept ids (optional)

widgets/allocation-process

### Citation source files (optional)

alpha-enh.md
"""


def test_parse_issue_builds_record():
    rec = parse_issue(BODY)
    assert rec["client"] == "alpha" and rec["product"] == "widgets"
    assert rec["memory"].startswith("Alpha requires")
    assert rec["related"] == ["widgets/allocation-process"]
    assert rec["citations"] == ["alpha-enh.md"]
    assert rec["status"] == "approved"


def test_validate_rejects_a_product_the_profile_does_not_declare(monkeypatch):
    """The allowlist is corpus vocabulary, so it is patched in rather than assumed."""
    monkeypatch.setattr(mod, "ALLOWED_PRODUCTS", {"widgets", "gadgets"})
    with pytest.raises(ValueError):
        validate_record({"client": "alpha", "product": "evil"})


def test_validate_skips_the_product_check_when_the_profile_declares_none(monkeypatch):
    """An empty allowlist means "not configured", not "reject everything". A validator
    that fails closed on valid data is worse than no validator."""
    monkeypatch.setattr(mod, "ALLOWED_PRODUCTS", set())
    validate_record({"client": "alpha", "product": "anything-at-all"})


def test_validate_rejects_unsafe_client():
    for bad in ("..", "../etc", "a/b", "", "Alpha/x", "alpha\n", "alpha ", " alpha"):
        with pytest.raises(ValueError):
            validate_record({"client": bad, "product": "widgets"})


def test_validate_accepts_clean():
    validate_record({"client": "alpha", "product": "widgets"})   # no raise


def test_slug():
    assert _slug("Second Scan!") == "second-scan"

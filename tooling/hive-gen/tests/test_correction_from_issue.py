import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "correction_from_issue", Path(__file__).resolve().parents[1] / "scripts" / "correction_from_issue.py")
mod = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(mod)

ISSUE = """### Target concept id

widgets/data-requirements

### Corrected fact

Duplicate slot numbers are not allowed.

### Rationale

Data Requirements Guide, Slots Import section.

### Citation source files

sprockets-sprockets-optimization-2020-data-requirements-guide.md

### Supersedes (optional)

_No response_
"""


def test_parse_issue(tmp_path):
    rec = mod.parse_issue(ISSUE)
    assert rec["corrects"] == "widgets/data-requirements"
    assert rec["product"] == "widgets"            # derived from corrects path
    assert "not allowed" in rec["correction"]
    assert rec["citations"] == ["sprockets-sprockets-optimization-2020-data-requirements-guide.md"]
    assert rec["supersedes"] == []
    assert rec["status"] == "approved"


def test_validate_record_rejects_traversal():
    import pytest
    # product ".." from a traversal target must be rejected
    with pytest.raises(ValueError):
        mod.validate_record({"corrects": "../../.github/workflows/evil", "product": ".."})


def test_validate_record_rejects_a_product_the_profile_does_not_declare(monkeypatch):
    """The allowlist is corpus vocabulary, so it is patched in rather than assumed."""
    monkeypatch.setattr(mod, "ALLOWED_PRODUCTS", {"widgets"})
    with pytest.raises(ValueError):
        mod.validate_record({"corrects": "widgets/a", "product": "evil",
                         "title": "t", "description": "d", "body": "b"})


def test_validate_record_skips_the_product_check_when_none_are_declared(monkeypatch):
    """Empty means "not configured", not "reject everything"."""
    monkeypatch.setattr(mod, "ALLOWED_PRODUCTS", set())
    mod.validate_record({"corrects": "anything/a", "product": "anything",
                     "title": "t", "description": "d", "body": "b"})


def test_validate_record_accepts_valid():
    # a real product/concept passes cleanly (no raise)
    mod.validate_record({"corrects": "widgets/data-requirements", "product": "widgets"})

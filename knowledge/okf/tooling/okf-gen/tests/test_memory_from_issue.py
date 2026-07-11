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

wms

### Title

Second scan at allocation confirm

### The lesson (de-personalised)

ALPHA requires a second verification scan before committing the pick.

### When it applies

ALPHA site only.

### Platform (optional)

wmos

### Related concept ids (optional)

wms/allocation-process

### Citation source files (optional)

alpha-enh.md
"""


def test_parse_issue_builds_record():
    rec = parse_issue(BODY)
    assert rec["client"] == "alpha" and rec["product"] == "wms"
    assert rec["memory"].startswith("ALPHA requires")
    assert rec["related"] == ["wms/allocation-process"]
    assert rec["citations"] == ["alpha-enh.md"]
    assert rec["status"] == "approved"


def test_validate_rejects_bad_product():
    with pytest.raises(ValueError):
        validate_record({"client": "alpha", "product": "evil"})


def test_validate_rejects_unsafe_client():
    for bad in ("..", "../etc", "a/b", "", "ALPHA/x", "alpha\n", "alpha ", " alpha"):
        with pytest.raises(ValueError):
            validate_record({"client": bad, "product": "wms"})


def test_validate_accepts_clean():
    validate_record({"client": "alpha", "product": "wms"})   # no raise


def test_slug():
    assert _slug("Second Scan!") == "second-scan"

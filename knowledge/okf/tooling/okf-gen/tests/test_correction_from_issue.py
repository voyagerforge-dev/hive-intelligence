import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "correction_from_issue", Path(__file__).resolve().parents[1] / "scripts" / "correction_from_issue.py")
mod = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(mod)

ISSUE = """### Target concept id

slotting/data-requirements

### Corrected fact

Duplicate slot numbers are not allowed.

### Rationale

Data Requirements Guide, Slots Import section.

### Citation source files

slotting-slotting-optimization-2020-data-requirements-guide.md

### Supersedes (optional)

_No response_
"""


def test_parse_issue(tmp_path):
    rec = mod.parse_issue(ISSUE)
    assert rec["corrects"] == "slotting/data-requirements"
    assert rec["product"] == "slotting"            # derived from corrects path
    assert "not allowed" in rec["correction"]
    assert rec["citations"] == ["slotting-slotting-optimization-2020-data-requirements-guide.md"]
    assert rec["supersedes"] == []
    assert rec["status"] == "approved"

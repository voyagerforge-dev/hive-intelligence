from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[5]   # repo root from okf-gen/tests


def test_memory_issue_form_wellformed():
    form = yaml.safe_load((ROOT / ".github/ISSUE_TEMPLATE/memory.yml").read_text())
    assert "okf-memory" in form["labels"]
    ids = {f.get("id") for f in form["body"]}
    assert {"client", "product", "title", "memory"} <= ids


def test_memory_action_fires_on_approved_label():
    assert "okf-memory-approved" in (ROOT / ".github/workflows/memory-from-issue.yml").read_text()
    assert "memory_from_issue.py" in (ROOT / ".github/workflows/memory-from-issue.yml").read_text()


def test_codeowners_covers_memory_dir():
    assert "clients/" in (ROOT / ".github/CODEOWNERS").read_text()

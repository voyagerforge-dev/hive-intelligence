"""GitHub surface for the memory and correction card flows.

These assert on **repository configuration**, not on code: the issue form, the
approved-label workflow, and the CODEOWNERS rules that guard the card
directories. That surface governs where memory and correction cards live, so it
belongs to whichever repository hosts the corpus, not to the tooling.

A workflow reaches the card parser as the installed
``hivegen-memory-from-issue`` command, which ships with the tooling. The
workflows themselves follow the content they act on. When the corpus is split
into its own repository, this surface goes with it and these tests skip rather
than fail.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]   # repo root: tests -> hive-gen -> tooling -> root

ISSUE_FORM = ROOT / ".github/ISSUE_TEMPLATE/memory.yml"
MEMORY_WORKFLOW = ROOT / ".github/workflows/memory-from-issue.yml"
CODEOWNERS = ROOT / "CODEOWNERS"

needs_github_surface = pytest.mark.skipif(
    not ISSUE_FORM.is_file(),
    reason="card GitHub surface not present (it lives with the corpus repository)",
)


@needs_github_surface
def test_memory_issue_form_wellformed():
    form = yaml.safe_load(ISSUE_FORM.read_text())
    assert "hive-memory" in form["labels"]
    ids = {f.get("id") for f in form["body"]}
    assert {"client", "product", "title", "memory"} <= ids


@needs_github_surface
def test_memory_action_fires_on_approved_label():
    text = MEMORY_WORKFLOW.read_text()
    assert "hive-memory-approved" in text
    # Both spellings pass on purpose: a corpus repository switches its workflow from the
    # in-tree script path to the installed command when it bumps its hive-gen pin, and this
    # must go red neither on a corpus that has migrated nor on one that has not yet.
    assert "hivegen-memory-from-issue" in text or "memory_from_issue.py" in text


@needs_github_surface
def test_codeowners_covers_memory_dir():
    text = CODEOWNERS.read_text()
    assert "clients/" in text
    assert "corrections/" in text  # regression guard: root CODEOWNERS must not be shadowed

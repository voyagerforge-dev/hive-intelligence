import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "new_correction", Path(__file__).resolve().parents[1] / "scripts" / "new_correction.py")
mod = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(mod)


def test_build_writes_scaffold(tmp_path):
    p = mod.build("slotting", "slotting/data-requirements", "Duplicate slots not allowed",
                  out_dir=tmp_path, timestamp="2026-07-09")
    text = p.read_text()
    assert p.parent.name == "corrections" and p.parent.parent.name == "slotting"
    assert "type: correction" in text
    assert "corrects: slotting/data-requirements" in text
    assert "status: draft" in text          # scaffold starts as draft
    assert "## Correction" in text and "## Rationale" in text

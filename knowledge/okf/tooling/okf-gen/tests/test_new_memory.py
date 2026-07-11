import importlib.util
from pathlib import Path

from okfgen.memory import memory_to_record

_spec = importlib.util.spec_from_file_location(
    "new_memory", Path(__file__).resolve().parents[1] / "scripts" / "new_memory.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)
build = mod.build


def test_build_scaffolds_draft(tmp_path):
    p = build("alpha", "wms", "Second scan at confirm", out_dir=tmp_path, timestamp="2026-07-12")
    assert p == tmp_path / "alpha" / "memory" / "second-scan-at-confirm.md"
    rec = memory_to_record(p.read_text())
    assert rec["client"] == "alpha" and rec["product"] == "wms"
    assert rec["status"] == "draft"
    assert rec["title"] == "Second scan at confirm"

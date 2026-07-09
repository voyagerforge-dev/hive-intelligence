import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "index_generate", Path(__file__).resolve().parents[1] / "scripts" / "index_generate.py")
mod = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(mod)


def test_index_excludes_corrections(tmp_path):
    (tmp_path / "wms").mkdir(); (tmp_path / "wms" / "corrections").mkdir()
    (tmp_path / "wms" / "c.md").write_text("---\ntitle: C\ntype: concept\ndescription: d\n---\n\nb\n")
    (tmp_path / "wms" / "corrections" / "fix.md").write_text(
        "---\ntitle: Fix\ntype: correction\ncorrects: wms/c\nstatus: approved\n---\n\n## Correction\n\nx\n")
    mod.generate(str(tmp_path))
    prod_index = (tmp_path / "wms" / "index.md").read_text()
    assert "/wms/c.md" in prod_index
    assert "corrections/fix" not in prod_index

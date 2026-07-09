import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "corrections_lint", Path(__file__).resolve().parents[1] / "scripts" / "corrections_lint.py")
mod = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(mod)


def _w(p, **fm):
    import yaml
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\n" + yaml.safe_dump(fm) + "---\n\nbody\n")


def test_lint_flags_dangling_and_conflict(tmp_path):
    _w(tmp_path / "wms" / "c.md", type="concept", title="C")
    _w(tmp_path / "wms" / "corrections" / "a.md", type="correction", corrects="wms/c", status="approved", title="A")
    _w(tmp_path / "wms" / "corrections" / "b.md", type="correction", corrects="wms/c", status="approved", title="B")
    _w(tmp_path / "wms" / "corrections" / "d.md", type="correction", corrects="wms/nope", status="approved", title="D")
    errors, warnings = mod.lint(tmp_path)
    assert any("wms/nope" in e for e in errors)              # dangling target
    assert any("wms/c" in w for w in warnings)               # >1 active on wms/c


def test_lint_bad_supersede_and_status(tmp_path):
    _w(tmp_path / "wms" / "c.md", type="concept", title="C")
    _w(tmp_path / "wms" / "corrections" / "new.md", type="correction", corrects="wms/c",
       status="approved", supersedes=["wms/corrections/old"], title="New")
    _w(tmp_path / "wms" / "corrections" / "old.md", type="correction", corrects="wms/c",
       status="approved", title="Old")   # should be superseded, still approved -> error
    errors, _ = mod.lint(tmp_path)
    assert any("wms/corrections/old" in e for e in errors)


def test_lint_flags_corrects_pointing_at_correction(tmp_path):
    _w(tmp_path / "wms" / "c.md", type="concept", title="C")
    _w(tmp_path / "wms" / "corrections" / "a.md", type="correction", corrects="wms/c", status="approved", title="A")
    # b.corrects points at correction a.md, not a concept -> dangling
    _w(tmp_path / "wms" / "corrections" / "b.md", type="correction", corrects="wms/corrections/a", status="approved", title="B")
    errors, _ = mod.lint(tmp_path)
    assert any("wms/corrections/b" in e and "wms/corrections/a" in e for e in errors)


def test_lint_conflict_warning_excludes_superseded(tmp_path):
    _w(tmp_path / "wms" / "c.md", type="concept", title="C")
    # 'new' supersedes 'old'; old is correctly flipped to superseded.
    _w(tmp_path / "wms" / "corrections" / "new.md", type="correction", corrects="wms/c",
       status="approved", supersedes=["wms/corrections/old"], title="New")
    _w(tmp_path / "wms" / "corrections" / "old.md", type="correction", corrects="wms/c",
       status="superseded", title="Old")
    errors, warnings = mod.lint(tmp_path)
    # only ONE live active correction (new) on wms/c -> no conflict warning, no errors
    assert errors == []
    assert not any("wms/c" in w for w in warnings)

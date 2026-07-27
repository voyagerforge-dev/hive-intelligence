# tests/test_normalize.py
from pathlib import Path
import pytest
from hiveprep import normalize as nz
from hiveprep.striptrim import StripStats

def test_pdf_is_copied_as_is(tmp_path):
    src = tmp_path / "a.pdf"; src.write_bytes(b"%PDF-1.4 fake")
    work = tmp_path / "work"
    res = nz.normalize_source(src, work)
    assert res.ok and res.pdf.exists()
    assert res.pdf.read_bytes() == b"%PDF-1.4 fake"
    assert res.strike_runs_removed == 0

def test_docx_is_striptrimmed_then_converted(tmp_path, monkeypatch):
    src = tmp_path / "b.docx"; src.write_bytes(b"docx-bytes")
    work = tmp_path / "work"
    calls = {}
    def fake_strip(s, o):
        Path(o).parent.mkdir(parents=True, exist_ok=True); Path(o).write_bytes(b"clean-docx")
        calls["stripped"] = Path(o)
        from hiveprep.striptrim import StripStats; return StripStats(runs_removed=3)
    def fake_to_pdf(s, outdir, timeout=180):
        assert s == calls["stripped"]               # converts the CLEANED docx
        p = Path(outdir) / (Path(s).stem + ".pdf"); p.write_bytes(b"%PDF clean"); return p
    monkeypatch.setattr(nz, "strip_struck", fake_strip)
    monkeypatch.setattr(nz, "lo_to_pdf", fake_to_pdf)
    res = nz.normalize_source(src, work)
    assert res.ok and res.strike_runs_removed == 3 and res.pdf.read_bytes() == b"%PDF clean"

def test_pptx_converted_no_striptrim(tmp_path, monkeypatch):
    src = tmp_path / "c.pptx"; src.write_bytes(b"pptx")
    work = tmp_path / "work"
    def fake_to_pdf(s, outdir, timeout=180):
        p = Path(outdir) / (Path(s).stem + ".pdf"); p.write_bytes(b"%PDF p"); return p
    monkeypatch.setattr(nz, "lo_to_pdf", fake_to_pdf)
    res = nz.normalize_source(src, work)
    assert res.ok and res.strike_runs_removed == 0

@pytest.mark.parametrize("ext", [".doc", ".docm", ".ppt", ".xls", ".xlsx"])
def test_legacy_office_formats_converted_no_striptrim(tmp_path, monkeypatch, ext):
    """Legacy/binary office formats go straight through LibreOffice (no docx strike-trim)."""
    src = tmp_path / f"c{ext}"; src.write_bytes(b"office")
    work = tmp_path / "work"
    def boom_strip(*a, **k):
        raise AssertionError("strike-trim must not run on non-docx formats")
    def fake_to_pdf(s, outdir, timeout=180):
        assert Path(s) == src                       # converts the ORIGINAL, not a cleaned copy
        p = Path(outdir) / (Path(s).stem + ".pdf"); p.write_bytes(b"%PDF x"); return p
    monkeypatch.setattr(nz, "strip_struck", boom_strip)
    monkeypatch.setattr(nz, "lo_to_pdf", fake_to_pdf)
    res = nz.normalize_source(src, work)
    assert res.ok and res.strike_runs_removed == 0 and res.pdf.read_bytes() == b"%PDF x"


def test_uppercase_pdf_normalized_to_lower_suffix(tmp_path):
    """A .PDF source must land as .pdf so transform (which lowercases the suffix) finds it."""
    src = tmp_path / "Guide.PDF"; src.write_bytes(b"%PDF up")
    res = nz.normalize_source(src, tmp_path / "work")
    assert res.ok and res.pdf.exists() and res.pdf.suffix == ".pdf"
    assert res.pdf.read_bytes() == b"%PDF up"


def test_unsupported_ext_flagged(tmp_path):
    src = tmp_path / "d.xyz"; src.write_bytes(b"x")
    res = nz.normalize_source(src, tmp_path / "work")
    assert not res.ok and "unsupported" in res.error.lower()

def test_failure_is_flagged_not_raised(tmp_path, monkeypatch):
    src = tmp_path / "e.docx"; src.write_bytes(b"d")
    def boom(*a, **k): raise RuntimeError("lo exploded")
    def fake_strip(s, o):
        Path(o).write_bytes(b"c"); return StripStats(0)
    monkeypatch.setattr(nz, "strip_struck", fake_strip)
    monkeypatch.setattr(nz, "lo_to_pdf", boom)
    res = nz.normalize_source(src, tmp_path / "work")
    assert not res.ok and "lo exploded" in res.error


def _mk_plan(root, *names):
    from hiveprep.curation_plan import Plan
    return Plan(scope="WMS", corpus_root=str(root), subtree=".",
                include=[{"path": n, "product": "WMS"} for n in names],
                exclude=[], dedup_groups=[], supersedes=[])


def _fake_normalize_source(src, work_dir, base_dir=None):
    from hiveprep.normalize import NormalizeResult
    p = work_dir / "pdf" / (Path(src).stem + ".pdf")
    p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"%PDF")
    return NormalizeResult(Path(src), ok=True, pdf=p)


def test_normalize_plan_skips_existing(tmp_path, monkeypatch):
    root = tmp_path / "src"; root.mkdir()
    (root / "a.docx").write_bytes(b"a"); (root / "b.docx").write_bytes(b"b")
    work = tmp_path / "work"
    exp_a = work / "pdf" / "a.pdf"; exp_a.parent.mkdir(parents=True); exp_a.write_bytes(b"%PDF a")  # already done
    calls = []
    def spy(src, wd, base_dir=None):
        calls.append(Path(src).name); return _fake_normalize_source(src, wd, base_dir)
    monkeypatch.setattr(nz, "normalize_source", spy)
    results = nz.normalize_plan(_mk_plan(root, "a.docx", "b.docx"), work, base_dir=root, jobs=2)
    assert calls == ["b.docx"]                       # a.docx skipped (output already exists)
    assert len(results) == 2 and all(r.ok for r in results)


def test_normalize_plan_processes_all_when_concurrent(tmp_path, monkeypatch):
    root = tmp_path / "src"; root.mkdir()
    for n in ("a", "b", "c", "d"):
        (root / f"{n}.docx").write_bytes(b"x")
    work = tmp_path / "work"
    monkeypatch.setattr(nz, "normalize_source", _fake_normalize_source)
    results = nz.normalize_plan(_mk_plan(root, "a.docx", "b.docx", "c.docx", "d.docx"),
                                work, base_dir=root, jobs=4, skip_existing=False)
    assert len(results) == 4 and {r.pdf.stem for r in results} == {"a", "b", "c", "d"}


def test_nested_same_name_no_collision(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    (src_dir / "a").mkdir(parents=True); (src_dir / "b").mkdir(parents=True)
    (src_dir / "a" / "guide.pdf").write_bytes(b"%PDF A")
    (src_dir / "b" / "guide.pdf").write_bytes(b"%PDF B")
    work = tmp_path / "work"
    results = nz.normalize_dir(src_dir, work)
    ok = [r for r in results if r.ok]
    assert len(ok) == 2
    bodies = sorted(p.read_bytes() for p in (work / "pdf").rglob("*.pdf"))
    assert bodies == [b"%PDF A", b"%PDF B"]   # both preserved, no overwrite

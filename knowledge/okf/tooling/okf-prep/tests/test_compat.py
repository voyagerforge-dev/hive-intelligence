# tests/test_compat.py
from pathlib import Path

import okfprep.compat as cc


def test_modern_and_text_copied_as_is(tmp_path):
    src = tmp_path / "a.docx"
    src.write_bytes(b"docx")
    res = cc.compat_normalize(src, tmp_path / "work", base_dir=tmp_path)
    assert res.ok and res.staged.suffix == ".docx" and res.staged.read_bytes() == b"docx"


def test_legacy_doc_upgraded_to_docx(tmp_path, monkeypatch):
    src = tmp_path / "b.doc"
    src.write_bytes(b"doc")

    def fake_office(s, outdir, target_ext, timeout=180):
        p = Path(outdir) / (Path(s).stem + "." + target_ext)
        p.write_bytes(b"converted")
        return p

    monkeypatch.setattr(cc, "lo_to_office", fake_office)
    res = cc.compat_normalize(src, tmp_path / "work", base_dir=tmp_path)
    assert res.ok and res.staged.suffix == ".docx"


def test_unsupported_binary_flagged(tmp_path):
    src = tmp_path / "c.emb"
    src.write_bytes(b"x")
    res = cc.compat_normalize(src, tmp_path / "work", base_dir=tmp_path)
    assert not res.ok and "unsupported" in res.error.lower()

# tests/test_libreoffice.py
import shutil
from pathlib import Path
import pytest
from okfprep import libreoffice as lo

def test_build_command_shape(tmp_path):
    cmd = lo.build_command(Path("/x/in.docx"), tmp_path)
    assert cmd[0] == "soffice"
    assert "--headless" in cmd and "--convert-to" in cmd
    assert "pdf" in cmd
    assert str(tmp_path) in cmd
    assert cmd[-1] == "/x/in.docx"
    # isolated profile prevents lock collisions when run in parallel
    assert any(a.startswith("-env:UserInstallation=") for a in cmd)

def test_to_pdf_raises_when_soffice_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(lo.shutil, "which", lambda _: None)
    with pytest.raises(lo.LibreOfficeError):
        lo.to_pdf(tmp_path / "in.docx", tmp_path)

@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")
def test_to_pdf_real_docx(tmp_path):
    import docx
    src = tmp_path / "r.docx"
    d = docx.Document(); d.add_paragraph("hello pdf"); d.save(src)
    pdf = lo.to_pdf(src, tmp_path)
    assert pdf.exists() and pdf.suffix == ".pdf" and pdf.stat().st_size > 0

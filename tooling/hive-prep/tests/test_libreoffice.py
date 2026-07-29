# tests/test_libreoffice.py
from pathlib import Path

import pytest

from hiveprep import libreoffice as lo


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

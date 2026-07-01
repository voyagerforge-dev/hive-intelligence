# src/okfprep/libreoffice.py
"""Convert DOCX/PPTX to PDF via LibreOffice headless.

`soffice` is a system dependency (not pip). We pass an isolated
-env:UserInstallation profile so concurrent conversions don't fight over the
default profile lock.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path


class LibreOfficeError(RuntimeError):
    pass


def build_command(src: Path, out_dir: Path, profile_dir: str | None = None) -> list[str]:
    profile = profile_dir or f"file://{tempfile.gettempdir()}/lo-{uuid.uuid4().hex}"
    return [
        "soffice", "--headless",
        f"-env:UserInstallation={profile}",
        "--convert-to", "pdf",
        "--outdir", str(out_dir),
        str(src),
    ]


def to_pdf(src: Path, out_dir: Path, timeout: int = 180) -> Path:
    """Convert `src` to PDF in `out_dir`; return the produced PDF path."""
    if shutil.which("soffice") is None:
        raise LibreOfficeError("LibreOffice 'soffice' not found on PATH")
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lo-") as prof:
        cmd = build_command(src, out_dir, profile_dir=f"file://{prof}")
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise LibreOfficeError(f"soffice timed out after {timeout}s on {src.name}") from e
        if proc.returncode != 0:
            raise LibreOfficeError(f"soffice failed ({proc.returncode}) on {src.name}: {proc.stderr[:300]}")
    pdf = out_dir / (src.stem + ".pdf")
    if not pdf.exists() or pdf.stat().st_size == 0:
        raise LibreOfficeError(f"soffice produced no PDF for {src.name}")
    return pdf

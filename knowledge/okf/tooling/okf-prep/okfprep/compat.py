# src/okfprep/compat.py
"""Format-compat normalize: make inputs Docling-ingestible WITHOUT extracting content.

Legacy office formats are upgraded in-place to their modern Docling-native
equivalent via LibreOffice headless; modern office / PDF / text formats are
copied as-is; everything else is flagged (opaque/binary). Failures are returned
as flagged results, never raised, so a batch run continues.

`lo_to_office` mirrors `libreoffice.py`'s soffice invocation: an isolated
`-env:UserInstallation` profile (so concurrent conversions don't fight over the
default profile lock) plus a timeout.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

_UPGRADE = {".doc": "docx", ".docm": "docx", ".ppt": "pptx", ".xls": "xlsx"}
_PASS = {".docx", ".pptx", ".xlsx", ".pdf", ".md", ".txt", ".csv", ".vm",
         ".xsd", ".xml", ".json", ".sql", ".properties", ".html"}


@dataclass
class CompatResult:
    source: Path
    ok: bool
    staged: Path | None = None
    error: str = ""


def lo_to_office(src: Path, out_dir: Path, target_ext: str, timeout: int = 180) -> Path:
    """Convert `src` to `target_ext` in `out_dir` via LibreOffice; return the output path."""
    if shutil.which("soffice") is None:
        raise RuntimeError("LibreOffice 'soffice' not found on PATH")
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lo-") as prof:
        cmd = ["soffice", "--headless", f"-env:UserInstallation=file://{prof}",
               "--convert-to", target_ext, "--outdir", str(out_dir), str(src)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"soffice timed out after {timeout}s on {src.name}") from e
    if proc.returncode != 0:
        raise RuntimeError(f"soffice failed ({proc.returncode}) on {src.name}: {proc.stderr[:300]}")
    out = out_dir / (src.stem + "." + target_ext)
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"soffice produced no {target_ext} for {src.name}")
    return out


def compat_normalize(src: Path, work_dir: Path, base_dir: Path) -> CompatResult:
    """Stage one file Docling-ingestible under `<work_dir>/staged/<rel>`.

    Operates on a single file in isolation. The caller (``stage.py``) is
    responsible for ensuring staged paths are unique across the batch — e.g.
    a legacy ``report.doc`` upgraded to ``report.docx`` can collide with a
    sibling ``report.docx``; family-aware ``dedup-formats`` removes such
    same-stem variants upstream, and ``stage`` validates manifest↔docs
    uniqueness before any upload.
    """
    staged_dir = work_dir / "staged"
    try:
        ext = src.suffix.lower()
        rel = src.relative_to(base_dir)
        if ext in _UPGRADE:
            out_dir = (staged_dir / rel).parent
            out_dir.mkdir(parents=True, exist_ok=True)
            staged = lo_to_office(src, out_dir, _UPGRADE[ext])
            return CompatResult(src, ok=True, staged=staged)
        if ext in _PASS:
            dst = (staged_dir / rel)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            return CompatResult(src, ok=True, staged=dst)
        return CompatResult(src, ok=False, error=f"unsupported (non-doc/binary) extension: {ext}")
    except Exception as e:  # flag, don't crash the batch
        return CompatResult(src, ok=False, error=str(e))

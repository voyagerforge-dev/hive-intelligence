# src/hiveprep/normalize.py
"""Normalize a source document to a PDF intermediate the transform step can render.

  DOCX                       -> strike-trim -> clean.docx -> (LibreOffice) PDF
  DOC/DOCM/PPT/PPTX/XLS/XLSX -> (LibreOffice) PDF   (treated clean; no strike-trim)
  PDF/.PDF                   -> copied as-is, suffix normalized to lowercase .pdf

Strike-trim (tracked-change / strikethrough removal) edits the docx XML directly, so it
only applies to the .docx format; the legacy/binary office formats go straight through
LibreOffice. Failures are returned as flagged results, never raised, so a batch run continues.
"""
from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .striptrim import strip_struck
from .libreoffice import to_pdf as lo_to_pdf

# .docx alone gets strike-trim; the rest are converted by LibreOffice as-is.
_STRIKE_TRIM = {".docx"}
_LO_CONVERT = {".docx", ".docm", ".doc", ".pptx", ".ppt", ".xls", ".xlsx"}
SUPPORTED = {".pdf"} | _LO_CONVERT


@dataclass
class NormalizeResult:
    source: Path
    ok: bool
    pdf: Path | None = None
    strike_runs_removed: int = 0
    error: str = ""


def normalize_source(src: Path, work_dir: Path, base_dir: Path | None = None) -> NormalizeResult:
    ext = src.suffix.lower()
    pdf_dir = work_dir / "pdf"
    clean_dir = work_dir / "clean"
    rel = src.relative_to(base_dir) if base_dir is not None else Path(src.name)
    if ext not in SUPPORTED:
        return NormalizeResult(src, ok=False, error=f"unsupported extension: {ext}")
    try:
        if ext == ".pdf":
            # normalize the suffix case (.PDF -> .pdf) so transform, which lowercases it, finds the file
            dst = (pdf_dir / rel).with_suffix(".pdf")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            return NormalizeResult(src, ok=True, pdf=dst)
        if ext in _STRIKE_TRIM:  # .docx: strike-trim the XML, then convert the cleaned copy
            clean = clean_dir / rel
            clean.parent.mkdir(parents=True, exist_ok=True)
            stats = strip_struck(src, clean)
            out_dir = pdf_dir / rel.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            pdf = lo_to_pdf(clean, out_dir)
            return NormalizeResult(src, ok=True, pdf=pdf, strike_runs_removed=stats.runs_removed)
        # all other office formats (.doc/.docm/.ppt/.pptx/.xls/.xlsx): plain LibreOffice conversion
        out_dir = pdf_dir / rel.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf = lo_to_pdf(src, out_dir)
        return NormalizeResult(src, ok=True, pdf=pdf)
    except Exception as e:  # flag, don't crash the batch
        return NormalizeResult(src, ok=False, error=str(e))


def normalize_plan(plan, work_dir: Path, base_dir: Path, jobs: int = 8,
                   skip_existing: bool = True) -> list[NormalizeResult]:
    """Normalize a plan's includes to PDF, concurrently. Each LibreOffice call uses an isolated
    profile so conversions are safe to run in parallel. `skip_existing` makes the run resumable:
    includes whose output PDF already exists are not redone."""
    pdf_dir = work_dir / "pdf"
    todo: list[Path] = []
    done: list[NormalizeResult] = []
    for e in plan.include:
        rel = Path(e["path"])
        out_pdf = pdf_dir / rel.with_suffix(".pdf")
        if skip_existing and out_pdf.exists():
            done.append(NormalizeResult(base_dir / rel, ok=True, pdf=out_pdf))
        else:
            todo.append(rel)

    def work(rel: Path) -> NormalizeResult:
        return normalize_source(base_dir / rel, work_dir, base_dir=base_dir)

    if jobs <= 1:
        processed = [work(r) for r in todo]
    else:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            processed = list(ex.map(work, todo))
    return done + processed


def normalize_dir(src_dir: Path, work_dir: Path) -> list[NormalizeResult]:
    resolved_work = work_dir.resolve()
    results = []
    for path in sorted(src_dir.rglob("*")):
        if not path.is_file():
            continue
        if resolved_work in path.resolve().parents:
            continue
        if path.suffix.lower() in SUPPORTED:
            results.append(normalize_source(path, work_dir, base_dir=src_dir))
    return results

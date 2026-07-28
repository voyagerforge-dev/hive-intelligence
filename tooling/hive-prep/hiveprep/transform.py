"""Route a normalized PDF to markdown: text-rich → Docling (pymupdf4llm fallback);
image-dominant scan → Qwen3.6-27B vision; already-text sources → passthrough fence.
Writes <atomic_dir>/<slug>.md with frontmatter (extracted_via records the tier)."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from hiveprep.curation_plan import Plan
from hiveprep.docling_client import DoclingError
from hiveprep.slugs import PASSTHROUGH_EXTS, assign_slugs, slugify
from hiveprep.stripper import strip_boilerplate

VISION_MIN_CHARS = 100
IMG_DOMINANT_FRAC = 0.5
VISION_MIN_IMG_PAGES = 0.5


def route_tier(avg_chars: float, img_page_frac: float, vision_min_chars: int = VISION_MIN_CHARS,
               vision_min_img_pages: float = VISION_MIN_IMG_PAGES) -> str:
    if avg_chars >= vision_min_chars:
        return "text"
    return "vision" if img_page_frac >= vision_min_img_pages else "text"


def pdf_text_profile(pdf: Path) -> dict:
    """pages, avg extractable chars/page, and img_page_frac (fraction of pages dominated by a
    single large image). Per-page largest image (not summed) so recursive small logos don't inflate."""
    import fitz

    doc = fitz.open(pdf)
    try:
        pages = doc.page_count
        if pages == 0:
            return {"pages": 0, "avg_chars": 0.0, "img_page_frac": 0.0}
        total_chars = dominant = 0
        for pg in doc:
            total_chars += len(pg.get_text("text"))
            area = pg.rect.get_area() or 1.0
            largest = 0.0
            for img in pg.get_images(full=True):
                for r in pg.get_image_rects(img[0]):
                    largest = max(largest, r.get_area() / area)
            if largest >= IMG_DOMINANT_FRAC:
                dominant += 1
        return {"pages": pages, "avg_chars": total_chars / pages, "img_page_frac": dominant / pages}
    finally:
        doc.close()


_DOTLEADER = re.compile(r"\.{4,}")
_DATA_URI_IMG = re.compile(r"!\[[^\]]*\]\(data:[^)]*\)")


def _clean_text_md(md: str) -> str:
    md = _DATA_URI_IMG.sub("", md)
    md = _DOTLEADER.sub(" ", md)
    return re.sub(r"\n{3,}", "\n\n", md).strip()


def _pymupdf4llm_markdown(pdf: Path) -> str:
    import pymupdf4llm
    return _clean_text_md(pymupdf4llm.to_markdown(str(pdf)))


def extract_text_markdown(pdf: Path, *, docling=None) -> str:
    """Text tier: prefer Docling (better tables/layout); fall back to local pymupdf4llm on any
    Docling failure or empty conversion, so the pipeline still runs with no GPU/Docling."""
    if docling is not None:
        try:
            return _clean_text_md(docling.to_markdown(pdf.name, pdf.read_bytes()))
        except DoclingError:
            pass
    return _pymupdf4llm_markdown(pdf)


def render_pdf_pages(pdf: Path, out_dir: Path, dpi: int = 100) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / pdf.stem
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), str(pdf), str(prefix)],
                   check=True, capture_output=True)
    return sorted(out_dir.glob(f"{pdf.stem}*.png"))


_FENCE_LANG = {".vm": "velocity", ".xsd": "xml", ".xml": "xml", ".json": "json",
               ".csv": "csv", ".properties": "properties", ".sql": "sql", ".txt": ""}


def passthrough_markdown(src: Path) -> str:
    lang = _FENCE_LANG.get(src.suffix.lower(), "")
    return f"```{lang}\n{src.read_text(errors='replace').strip()}\n```"


@dataclass
class TransformResult:
    source_doc: str
    ok: bool
    md_path: Path | None = None
    pages: int = 0
    tier: str = ""       # text | vision | passthrough | skip
    error: str = ""


@dataclass
class RouteResult:
    path: str
    slug: str
    tier: str            # text | vision | passthrough | missing
    pages: int = 0
    avg_chars: float = 0.0
    img_page_frac: float = 0.0


def _write_atomic(atomic_dir: Path, source_doc: str, slug: str, tier: str, body_md: str) -> Path:
    title = Path(source_doc).stem
    fm = (f'---\ntitle: "{title}"\nslug: {slug}\nsource_doc: "{source_doc}"\n'
          f"extracted_via: {tier}\nstatus: active\n---\n\n")
    atomic_dir.mkdir(parents=True, exist_ok=True)
    out = atomic_dir / f"{slug}.md"
    out.write_text(fm + f"# {title}\n\n" + body_md + "\n")
    return out


def _strip(body: str, strip_product: str | None) -> str:
    """Scrub copyright/trademark/confidentiality/page-number boilerplate from converted markdown.
    No-op when strip_product is None (stripping disabled). Not applied to passthrough (fenced code)."""
    return strip_boilerplate(body, product=strip_product).text if strip_product else body


def transform_pdf(pdf: Path, source_doc: str, product: str, atomic_dir: Path, *,
                  docling, vision, render_dir: Path, vision_min_chars: int = VISION_MIN_CHARS,
                  prefer_docling: bool = True, force_tier: str | None = None,
                  strip_product: str | None = None, slug: str | None = None) -> TransformResult:
    slug = slug or slugify(product, source_doc)
    try:
        prof = pdf_text_profile(pdf)
        if prof["pages"] == 0:
            return TransformResult(source_doc, ok=False, error="no pages in PDF")
        auto = route_tier(prof["avg_chars"], prof["img_page_frac"], vision_min_chars)
        use_text = force_tier == "text" or (force_tier is None and auto == "text")
        if use_text:
            body = extract_text_markdown(pdf, docling=docling if prefer_docling else None)
            out = _write_atomic(atomic_dir, source_doc, slug, "text", _strip(body, strip_product))
            return TransformResult(source_doc, ok=True, md_path=out, pages=prof["pages"], tier="text")
        pages = render_pdf_pages(pdf, render_dir)
        if not pages:
            return TransformResult(source_doc, ok=False, error="no pages rendered")
        body = "\n\n".join(vision.describe_image(p.read_bytes()) for p in pages)
        out = _write_atomic(atomic_dir, source_doc, slug, "vision", _strip(body, strip_product))
        return TransformResult(source_doc, ok=True, md_path=out, pages=len(pages), tier="vision")
    except Exception as e:  # noqa: BLE001, flag, never crash the batch
        return TransformResult(source_doc, ok=False, error=str(e))


def transform_plan(plan: Plan, work_dir: Path, *, docling, vision,
                   vision_min_chars: int = VISION_MIN_CHARS, prefer_docling: bool = True,
                   skip_existing: bool = True, routing: dict[str, str] | None = None,
                   strip_product: str | None = None) -> list[TransformResult]:
    pdf_root, atomic, render = work_dir / "pdf", work_dir / "atomic", work_dir / "_pages"
    corpus_root = Path(plan.corpus_root)
    valid: list[dict] = []
    results: list[TransformResult] = []
    for e in plan.include:
        if not e.get("path"):
            results.append(TransformResult("<missing path>", ok=False, error="include entry missing 'path'"))
        else:
            valid.append(e)
    for e, slug in zip(valid, assign_slugs(valid)):
        rel = Path(e["path"]); product = e.get("product", "WMS"); ext = rel.suffix.lower()
        if skip_existing and (atomic / f"{slug}.md").exists():
            results.append(TransformResult(rel.name, ok=True, md_path=atomic / f"{slug}.md", tier="skip"))
            continue
        if ext in PASSTHROUGH_EXTS:
            src = corpus_root / rel
            if not src.exists():
                results.append(TransformResult(rel.name, ok=False, error=f"source missing: {src}"))
                continue
            try:
                out = _write_atomic(atomic, rel.name, slug, "passthrough", passthrough_markdown(src))
                results.append(TransformResult(rel.name, ok=True, md_path=out, pages=1, tier="passthrough"))
            except Exception as ex:  # noqa: BLE001
                results.append(TransformResult(rel.name, ok=False, error=str(ex)))
            continue
        pdf = pdf_root / rel.with_suffix(".pdf")
        if not pdf.exists():
            results.append(TransformResult(rel.name, ok=False, error=f"normalized PDF missing: {pdf}"))
            continue
        results.append(transform_pdf(
            pdf, rel.name, product, atomic, docling=docling, vision=vision, render_dir=render,
            vision_min_chars=vision_min_chars, prefer_docling=prefer_docling,
            force_tier=(routing or {}).get(slug), strip_product=strip_product, slug=slug))
    return results


def route_plan(plan: Plan, work_dir: Path, vision_min_chars: int = VISION_MIN_CHARS) -> list[RouteResult]:
    """GPU-free precheck: profile every normalized PDF and flag its tier so the vision workload
    can be quantified/reviewed before any Qwen pass runs."""
    pdf_root, corpus_root = work_dir / "pdf", Path(plan.corpus_root)
    valid: list[dict] = []
    out: list[RouteResult] = []
    for e in plan.include:
        if not e.get("path"):
            out.append(RouteResult(str(e), "", "missing"))
        else:
            valid.append(e)
    for e, slug in zip(valid, assign_slugs(valid)):
        rel = Path(e["path"]); ext = rel.suffix.lower()
        if ext in PASSTHROUGH_EXTS:
            ok = (corpus_root / rel).exists()
            out.append(RouteResult(str(rel), slug, "passthrough" if ok else "missing", 1 if ok else 0))
            continue
        pdf = pdf_root / rel.with_suffix(".pdf")
        if not pdf.exists():
            out.append(RouteResult(str(rel), slug, "missing")); continue
        prof = pdf_text_profile(pdf)
        if prof["pages"] == 0:
            out.append(RouteResult(str(rel), slug, "missing")); continue
        tier = route_tier(prof["avg_chars"], prof["img_page_frac"], vision_min_chars)
        out.append(RouteResult(str(rel), slug, tier, prof["pages"],
                               round(prof["avg_chars"], 1), round(prof["img_page_frac"], 3)))
    return out

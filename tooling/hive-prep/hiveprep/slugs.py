"""Slug helpers for the atomic-markdown corpus (ported from gwen_prep.manifest).

Only the slug-identity cluster lives here, no R2/manifest-record/convert-routing
logic. See hiveprep.validate for slug *uniqueness* validation across the corpus.
"""
from __future__ import annotations

import re
from pathlib import Path

# Already-text source formats (Velocity label templates, XML schemas, CSV reference data, etc.).
# These are ingested AS-IS by downstream; here they only steer slug-tagging so a .xsd schema never
# collides with a same-stem .xlsx/.docx (whose ext-less slug would otherwise be identical).
PASSTHROUGH_EXTS = {".vm", ".xsd", ".xml", ".json", ".txt", ".csv", ".properties", ".sql"}


def slugify(product: str, name: str) -> str:
    stem = Path(name).stem
    kebab = re.sub(r"[^a-z0-9]+", "-", f"{product} {stem}".lower()).strip("-")
    return re.sub(r"-{2,}", "-", kebab)


def doc_slug(product: str, rel_path: str) -> str:
    """Folder-qualified slug from the corpus-relative path (extension dropped).

    Unlike `slugify` (basename only), this includes the folder path, so same-named docs in
    different module folders get distinct slugs, preventing silent atomic/R2 overwrites.
    Same-folder .doc/.docx pairs still collapse to one slug (extension dropped); those are
    format-duplicates resolved by curation dedup.
    """
    base = str(Path(rel_path).with_suffix(""))
    kebab = re.sub(r"[^a-z0-9]+", "-", f"{product} {base}".lower()).strip("-")
    return re.sub(r"-{2,}", "-", kebab)


def passthrough_slug(product: str, rel_path: str) -> str:
    """Slug for a passthrough file, folder-qualified AND extension-tagged, so a .xsd schema never
    collides with a same-stem .xlsx/.docx (whose ext-less slug would otherwise be identical)."""
    return f"{doc_slug(product, rel_path)}-{Path(rel_path).suffix.lower().lstrip('.')}"


def _base_slug(entry: dict) -> str:
    product, path = entry.get("product", "WMS"), entry["path"]
    return passthrough_slug(product, path) if Path(path).suffix.lower() in PASSTHROUGH_EXTS else doc_slug(product, path)


def assign_slugs(includes: list) -> list[str]:
    """Final, globally-unique slug per include (plan order). The first use of a base slug keeps it
    clean; later collisions get -2, -3, … so distinct docs that kebab to the same base (e.g.
    'Work Order.pdf' vs 'Work_Order.pdf') never overwrite each other."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for e in includes:
        base = _base_slug(e)
        n = seen.get(base, 0) + 1
        seen[base] = n
        out.append(base if n == 1 else f"{base}-{n}")
    return out

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


class MissingProduct(ValueError):
    """A curation-plan include entry with no `product`.

    Its own type so `route`, `transform` and `stamp` can turn exactly this failure into a
    clean one-line refusal: catching bare `ValueError` there would swallow unrelated
    failures and present them to an operator as a plan problem. `ValueError` stays the base
    class, so callers that only care that a bad plan is refused are unaffected.
    """


def entry_product(entry: dict) -> str:
    """The product a curation-plan include entry is filed under. There is no default.

    A missing one used to fall back to the literal `WMS`, the domain Hive was first built
    for. That is a wrong answer rather than a safe one: the product is the leading segment
    of every slug, so a mis-defaulted entry writes its atomic doc, its R2 key and its
    stamped frontmatter under a product the corpus may not even contain, and nothing
    downstream can tell that apart from a deliberate choice. Refusing names the entry, which
    is a problem an operator can fix; `hiveprep validate-plan` is the gate that lists this
    corpus's known products and reports every offending entry at once.
    """
    product = str(entry.get("product") or "").strip()
    if product:
        return product
    raise MissingProduct(
        f"curation plan include {entry.get('path') or '<no path>'!r} has no `product`. "
        "It has no default: the product is the first segment of the slug every later "
        "stage keys on. Run `hiveprep validate-plan` for this corpus's known products and "
        "every entry that is missing one."
    )


def _base_slug(entry: dict) -> str:
    product, path = entry_product(entry), entry["path"]
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

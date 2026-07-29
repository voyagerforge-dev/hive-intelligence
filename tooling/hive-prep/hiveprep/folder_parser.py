"""Folder path parser, extracts classification hints from directory segments.

Document repositories are commonly organised in hierarchies like:
    ClientName/Product/Version/DocumentCategory/filename.pdf
    General/Product/DocumentCategory/filename.pdf
    Product/ClientName/Version/docs/filename.docx

The parser uses heuristics to identify products, version patterns and document
category keywords from folder names. These hints supplement classification rather
than replacing it: they provide a strong prior for the majority of files that sit in
a clear folder structure.

Version and category matching are generic. **Product matching is not**: product names
are one corpus's vocabulary, so they come from the corpus profile. With no profile,
product hinting is simply off.
"""
from __future__ import annotations

import re

from hiveprep.profile import load_product_aliases

# ── Product names ────────────────────────────────────────────────────

# Populated from the corpus profile at call time, not baked in here. See hiveprep.profile.


# ── Version patterns ─────────────────────────────────────────────────

# Matches: v2024, v2023.1, v9.2, 2024.1, 9.2.1, v2024-SP1, etc.
VERSION_PATTERN = re.compile(
    r"^v?(\d{4}(?:\.\d+)*(?:-\w+)?|\d+\.\d+(?:\.\d+)*(?:-\w+)?)$",
    re.IGNORECASE,
)

# ── Document category keywords ───────────────────────────────────────

# Map of normalized folder name keywords → doc_type hints
CATEGORY_KEYWORDS: dict[str, str] = {
    "config": "config-guide",
    "configuration": "config-guide",
    "config guide": "config-guide",
    "config guides": "config-guide",
    "configuration guide": "config-guide",
    "user manual": "user-manual",
    "user manuals": "user-manual",
    "user guide": "user-manual",
    "user guides": "user-manual",
    "manuals": "user-manual",
    "release note": "release-notes",
    "release notes": "release-notes",
    "releases": "release-notes",
    "what's new": "release-notes",
    "api": "api-reference",
    "api reference": "api-reference",
    "api doc": "api-reference",
    "api docs": "api-reference",
    "api documentation": "api-reference",
    "rest api": "api-reference",
    "technical spec": "technical-spec",
    "technical specification": "technical-spec",
    "tech spec": "technical-spec",
    "specs": "technical-spec",
    "specification": "technical-spec",
    "implementation": "implementation-guide",
    "implementation guide": "implementation-guide",
    "impl guide": "implementation-guide",
    "impl": "implementation-guide",
    "deployment": "implementation-guide",
    "setup": "implementation-guide",
    "install": "implementation-guide",
    "installation": "implementation-guide",
    "troubleshoot": "troubleshooting",
    "troubleshooting": "troubleshooting",
    "issue": "troubleshooting",
    "known issues": "troubleshooting",
    "faq": "faq",
    "frequently asked": "faq",
    "training": "training-material",
    "training material": "training-material",
    "training materials": "training-material",
    "course": "training-material",
    "courses": "training-material",
    "e-learning": "training-material",
    "best practice": "best-practices",
    "best practices": "best-practices",
    "bp": "best-practices",
}

# ── Segment classifier ───────────────────────────────────────────────

# Known "general" / non-client folder names (case-insensitive)
GENERAL_FOLDERS = frozenset({
    "general", "shared", "common", "public", "global",
    "documentation", "docs", "documents", "library",
    "resources", "reference", "templates",
})


def _normalize(segment: str) -> str:
    """Lowercase, strip whitespace, collapse internal whitespace."""
    return " ".join(segment.lower().strip().split())


def _match_product(segment: str, aliases: dict[str, str]) -> str | None:
    """Match a folder segment against the corpus profile's product aliases."""
    return aliases.get(_normalize(segment))


def _match_version(segment: str) -> str | None:
    """Try to match a folder segment to a version pattern."""
    m = VERSION_PATTERN.match(segment.strip())
    return m.group(1) if m else None


def _match_category(segment: str) -> str | None:
    """Try to match a folder segment to a document category."""
    norm = _normalize(segment)
    return CATEGORY_KEYWORDS.get(norm)


def _is_general_folder(segment: str) -> bool:
    """Check if this segment is a known non-client folder name."""
    return _normalize(segment) in GENERAL_FOLDERS


# ── Main parser ──────────────────────────────────────────────────────

def parse_folder_segments(relative_path: str, segments: list[str],
                          product_aliases: dict[str, str] | None = None) -> dict:
    """Parse folder segments into classification hints.

    Args:
        relative_path: Full relative path (for context, not currently used).
        segments: List of folder names from root to parent of file.

    Returns:
        Dict with optional keys: client_hint, product_hint, version_hint,
        category_hint. Missing keys mean no hint was extracted.

    Strategy:
        Walk segments left to right. The first segment that matches a product
        or is a known general folder sets the context. Remaining segments
        are tested for version, category, and (if not general) client.
    """
    aliases = load_product_aliases() if product_aliases is None else product_aliases
    hints: dict[str, str] = {}
    client_candidates: list[str] = []

    for seg in segments:
        # Try product
        if "product_hint" not in hints:
            product = _match_product(seg, aliases)
            if product:
                hints["product_hint"] = product
                continue

        # Try version
        if "version_hint" not in hints:
            version = _match_version(seg)
            if version:
                hints["version_hint"] = version
                continue

        # Try category
        if "category_hint" not in hints:
            category = _match_category(seg)
            if category:
                hints["category_hint"] = category
                continue

        # Not product, version, or category, could be client or noise
        if not _is_general_folder(seg):
            client_candidates.append(seg)

    # First unmatched non-general segment is likely the client
    if client_candidates and "client_hint" not in hints:
        hints["client_hint"] = client_candidates[0]

    return hints

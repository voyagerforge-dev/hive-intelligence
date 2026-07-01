"""Load WMS atomic markdown and slice it into a generatable functional area.

Two slice mechanisms:
  - Legacy: ``is_wave_replen`` filename-keyword match (the original Wave/Replenishment slice).
  - Preferred: ``topics=`` — filter on the curator-assigned ``topic:`` frontmatter, so okfgen
    can be run one functional area at a time. ``AREAS`` groups the corpus's ~30 topics into
    coherent areas; ``load_area_local`` resolves an area name to its docs.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

# Wave/Replenishment functional area — name-keyword match (the original slice).
_WAVE_REPLEN = ("wave", "replen", "replenishment", "shipping-wave", "pre-wave",
                "fs-300", "fs300", "outbound-planning", "wave-inquiry")

# Functional areas → the exact `topic:` frontmatter values the curator assigned. Run okfgen
# one area at a time (SLICE_AREA / load_area_local) so each gets its own taxonomy and no single
# taxonomy call has to span the whole 1,239-doc corpus.
AREAS: dict[str, tuple[str, ...]] = {
    "inbound": ("Receiving", "Preceiving", "Putaway", "RF Inbound"),
    "inventory": ("Inventory Management",),
    "outbound": ("Outbound Distribution", "RF Outbound"),
    "transportation": ("Transportation Execution",),
    "yard": ("Yard Management",),
    "task": ("Task Mangement", "Resource Management", "Workload Management"),
    "system-control": ("System Control",),
    "interfaces": ("Interfaces",),
    "platform": ("SCPP platform / install", "WMOS platform architecture"),
    "reporting-labels": ("WMS reporting", "Labels"),
    "config": ("Configuration Workflows", "Common Update Documents", "WMS process/config"),
    "training": ("WMS technical training", "WMS user guide"),
    "release-notes": ("WMOS release notes",),
}


def is_wave_replen(name: str) -> bool:
    low = name.lower()
    return any(kw in low for kw in _WAVE_REPLEN)


@dataclass(frozen=True)
class Doc:
    id: str
    name: str
    text: str


def frontmatter_topic(text: str) -> str:
    """The `topic:` value from an atomic doc's YAML frontmatter ("" if none/unparseable)."""
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return ""
    return str(fm.get("topic", "") or "").strip()


def load_docs(s3, bucket: str, prefix: str, *, only_wave_replen: bool = True) -> list[Doc]:
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    out: list[Doc] = []
    for obj in resp.get("Contents", []):
        key = obj["Key"]
        if not key.endswith(".md"):
            continue
        if only_wave_replen and not is_wave_replen(key):
            continue
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        text = body.decode() if isinstance(body, bytes) else str(body)
        out.append(Doc(id=key, name=key, text=text))
    return out


def load_docs_local(root, *, only_wave_replen: bool = True,
                    topics: Iterable[str] | None = None) -> list[Doc]:
    """Read atomic markdown from a local directory. When ``topics`` is given, select docs whose
    ``topic:`` frontmatter is in that set (case-insensitive), ignoring the wave/replen keyword
    filter. Otherwise fall back to the legacy ``only_wave_replen`` filename filter."""
    root = Path(root)
    want = {t.strip().lower() for t in topics} if topics is not None else None
    out: list[Doc] = []
    for path in sorted(root.glob("*.md")):
        text = path.read_text()
        if want is not None:
            if frontmatter_topic(text).lower() not in want:
                continue
        elif only_wave_replen and not is_wave_replen(path.name):
            continue
        out.append(Doc(id=path.name, name=path.name, text=text))
    return out


def load_area_local(root, area: str) -> list[Doc]:
    """Load the atomic docs for a named functional area (see ``AREAS``)."""
    if area not in AREAS:
        raise KeyError(f"unknown area '{area}'; known: {sorted(AREAS)}")
    return load_docs_local(root, topics=AREAS[area])

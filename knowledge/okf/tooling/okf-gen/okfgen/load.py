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
    # WMOS guide/manual chapters, re-topiced out of the generic "WMS reference doc" bucket
    # (see okfprep/retopic classifier). Guide-overview cards complement the FS concept cards.
    "guide-outbound": ("Guide: Outbound Fulfillment",),
    "guide-inventory": ("Guide: Inventory Counting",),
    "guide-shipping-docs": ("Guide: Shipping Documents",),
    "guide-parcel-carrier": ("Guide: Parcel Carrier",),
    "guide-platform-admin": ("Guide: Platform Admin",),
    "guide-retail-compliance": ("Guide: Retail Compliance",),
    "guide-store-assortment": ("Guide: Store Assortment",),
    "guide-labor-task": ("Guide: Labor Task",),
    "guide-integration": ("Guide: Integration",),
    "guide-transportation": ("Guide: Transportation Routing",),
    "guide-yard": ("Guide: Yard",),
    "guide-reports": ("Guide: Reports",),
    # oSCI (Supply Chain Intelligence) — Cognos-based analytics repurposed for WMOS.
    "osci-frameworks": ("oSCI Frameworks",),
    "osci-analytics": ("oSCI Analytics Deliverables",),
    "osci-workspaces": ("oSCI Workspaces & Reports",),
    "osci-architecture": ("oSCI Architecture & Environment",),
    # Slotting Optimization — warehouse slot-optimization product on SCPP.
    "slotting-algorithms": ("Slotting Algorithms & Analysis",),
    "slotting-config": ("Slotting Configuration & Setup",),
    "slotting-integration": ("Slotting Integration",),
    "slotting-overview": ("Slotting Overview & Release Notes",),
    # Labour Management — workforce performance-management product on SCPP.
    "lm-employee-reports": ("LM Employee & Job-Function Reports",),
    "lm-team-standards": ("LM Team Standards & Quality",),
    "lm-payroll-scheduling": ("LM Payroll, Scheduling & Staffing",),
    "lm-events-operations": ("LM Events, Activity & Operations",),
    "lm-config-deployment": ("LM Configuration & Deployment",),
    "lm-interfaces-data": ("LM Interfaces & Data",),
}


@dataclass(frozen=True)
class SubArea:
    """A keyword sub-slice *within* one or more topics, for topics too large/heterogeneous to
    generate as one area (e.g. Interfaces, System Control). A doc matches when its ``topic:`` is in
    ``topics`` AND its filename contains one of ``include`` (or ``include`` is empty) AND its
    filename contains none of ``exclude``. ``exclude`` keeps sibling sub-slices disjoint and lets a
    remainder slice (empty ``include``) sweep whatever the named families didn't claim."""
    topics: tuple[str, ...]
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


# Keyword sub-slices for the two oversized single-topic areas. Filename keywords are the stable
# curator naming (…-interfaces-<family>-…, …-system-control-<family>-…). Sub-slices sharing a topic
# are disjoint: each names its family in ``include``; the remainder slice ``exclude``s the others.
_IFACE = ("Interfaces",)
_IFACE_HOST = ("Interfaces", "WMS integration/interfaces")
_SYSCTL = ("System Control",)
SUBAREAS: dict[str, SubArea] = {
    # Interfaces (229) + MHE integration (6) + WMS integration/interfaces (5)
    "if-lm-hooks": SubArea(_IFACE, include=("labor-management",)),
    "if-mhe": SubArea(("Interfaces", "MHE integration"), include=("mhe",),
                      exclude=("xsds-and-mapping-sheets",)),
    "if-billing-hooks": SubArea(_IFACE, include=("billing-integration",)),
    "if-voice": SubArea(_IFACE, include=("voice",)),
    "if-carrier": SubArea(_IFACE, include=("newgistics", "dynamic-routing")),
    "if-mapping-sheets": SubArea(_IFACE, include=("xsds-and-mapping-sheets",)),
    "if-host-data": SubArea(_IFACE_HOST, exclude=(
        "labor-management", "mhe", "billing-integration", "voice",
        "newgistics", "dynamic-routing", "xsds-and-mapping-sheets")),
    # System Control (111) — sc-purge claims all purge/archive; siblings exclude it.
    "sc-purge": SubArea(_SYSCTL, include=("purge", "archive")),
    "sc-print-label": SubArea(_SYSCTL, include=(
        "print-queue", "printer", "barcode", "smartlabel", "label-translation"),
        exclude=("purge", "archive")),
    "sc-message-i18n": SubArea(_SYSCTL, include=(
        "message-log", "message-lookup", "message-master", "literal-translation",
        "report-translation", "text-inq", "country-inquiry", "international-decimal",
        "send-message"), exclude=("purge", "archive")),
    "sc-admin": SubArea(_SYSCTL, exclude=(
        "purge", "archive", "print-queue", "printer", "barcode", "smartlabel",
        "label-translation", "message-log", "message-lookup", "message-master",
        "literal-translation", "report-translation", "text-inq", "country-inquiry",
        "international-decimal", "send-message")),
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
                    topics: Iterable[str] | None = None,
                    name_include: Iterable[str] | None = None,
                    name_exclude: Iterable[str] | None = None) -> list[Doc]:
    """Read atomic markdown from a local directory. When ``topics`` is given, select docs whose
    ``topic:`` frontmatter is in that set (case-insensitive), ignoring the wave/replen keyword
    filter. ``name_include``/``name_exclude`` further narrow by filename substring (lower-cased):
    a doc is kept only if its filename contains an ``include`` keyword (when any are given) and no
    ``exclude`` keyword — this is how sub-slices carve one topic. Without ``topics`` we fall back to
    the legacy ``only_wave_replen`` filename filter."""
    root = Path(root)
    want = {t.strip().lower() for t in topics} if topics is not None else None
    inc = tuple(k.lower() for k in name_include) if name_include else ()
    exc = tuple(k.lower() for k in name_exclude) if name_exclude else ()
    out: list[Doc] = []
    for path in sorted(root.glob("*.md")):
        text = path.read_text()
        if want is not None:
            if frontmatter_topic(text).lower() not in want:
                continue
        elif only_wave_replen and not is_wave_replen(path.name):
            continue
        low = path.name.lower()
        if inc and not any(k in low for k in inc):
            continue
        if exc and any(k in low for k in exc):
            continue
        out.append(Doc(id=path.name, name=path.name, text=text))
    return out


def load_area_local(root, area: str) -> list[Doc]:
    """Load the atomic docs for a named functional area (see ``AREAS``)."""
    if area not in AREAS:
        raise KeyError(f"unknown area '{area}'; known: {sorted(AREAS)}")
    return load_docs_local(root, topics=AREAS[area])


def load_subarea_local(root, name: str) -> list[Doc]:
    """Load the atomic docs for a named keyword sub-slice (see ``SUBAREAS``)."""
    if name not in SUBAREAS:
        raise KeyError(f"unknown sub-area '{name}'; known: {sorted(SUBAREAS)}")
    sa = SUBAREAS[name]
    return load_docs_local(root, topics=sa.topics,
                           name_include=sa.include or None,
                           name_exclude=sa.exclude or None)

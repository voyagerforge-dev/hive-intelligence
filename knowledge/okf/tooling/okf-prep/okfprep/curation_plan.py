"""Load + validate wms-curation.yaml. Validation is deterministic; a bad plan refuses to run."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import yaml
from okfprep.validate import DOC_TYPES   # DRY: single source of doc-type enum

PLATFORMS = {"SCPP", "SCALE", "Active"}
PRODUCTS = {"WMS", "LMS", "Slotting", "Omni", "OMS", "Billing Management", "oSCI"}

@dataclass
class Plan:
    scope: str
    corpus_root: str
    subtree: str
    include: list
    exclude: list
    dedup_groups: list
    supersedes: list

def load_plan(path: Path) -> Plan:
    d = yaml.safe_load(Path(path).read_text()) or {}
    return Plan(
        scope=d.get("scope", ""), corpus_root=d.get("corpus_root", ""), subtree=d.get("subtree", ""),
        include=d.get("include") or [], exclude=d.get("exclude") or [],
        dedup_groups=d.get("dedup_groups") or [], supersedes=d.get("supersedes") or [],
    )

def validate_plan(plan: Plan, corpus_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    root = Path(corpus_root) if corpus_root else Path(plan.corpus_root)
    inc_paths = {e.get("path") for e in plan.include}
    exc_paths = {e.get("path") for e in plan.exclude}
    for path in inc_paths & exc_paths:
        errors.append(f"'{path}' is in both include and exclude")
    for e in plan.include:
        p = e.get("path")
        if not p or not (root / p).exists():
            errors.append(f"include path missing on disk: '{p}'")
        if e.get("platform") not in PLATFORMS:
            errors.append(f"{p}: invalid platform '{e.get('platform')}'")
        if e.get("product") not in PRODUCTS:
            errors.append(f"{p}: invalid product '{e.get('product')}'")
        if e.get("doc_type") not in DOC_TYPES:
            errors.append(f"{p}: invalid doc_type '{e.get('doc_type')}'")
    for g in plan.dedup_groups:
        keep, drop = g.get("keep"), set(g.get("drop") or [])
        if keep in drop:
            errors.append(f"dedup group keep '{keep}' also listed in drop")
        if keep and not (root / keep).exists():
            errors.append(f"dedup keep path missing on disk: '{keep}'")
        for d in (g.get("drop") or []):
            if d and not (root / d).exists():
                errors.append(f"dedup drop path missing on disk: '{d}'")
    return errors


# A doc is only a "format variant" of another when they're the SAME application format FAMILY (e.g.
# .doc/.docx, .ppt/.pptx, .xls/.xlsx). Same-stem files of DIFFERENT families (a .xsd schema next to a
# .xlsx mapping sheet, a .vm template next to a .docx) are DISTINCT artifacts — never collapse them.
_FMT_FAMILY = {".doc": "word", ".docx": "word", ".docm": "word", ".rtf": "word",
               ".ppt": "ppt", ".pptx": "ppt",
               ".xls": "xls", ".xlsx": "xls"}
# Within a family, keep the richest/cleanest representation. Lower index = preferred.
_FMT_PRIORITY = [".docx", ".docm", ".doc", ".rtf", ".pptx", ".ppt", ".xlsx", ".xls"]


def _fmt_family(path: str) -> str:
    """Format family for variant-dedup; extensions outside a known family are their own singleton."""
    ext = Path(path).suffix.lower()
    return _FMT_FAMILY.get(ext, ext)


def _fmt_rank(path: str) -> int:
    ext = Path(path).suffix.lower()
    return _FMT_PRIORITY.index(ext) if ext in _FMT_PRIORITY else len(_FMT_PRIORITY)


def dedup_format_variants(plan: Plan) -> Plan:
    """Collapse same-document format variants — same folder + stem AND same format family — keeping
    the richest format and recording the rest as dedup_groups. Same-stem files of different families
    (e.g. a .xsd schema beside a .xlsx mapping sheet) are kept as distinct includes; cross-folder
    same-name docs are never merged."""
    from collections import defaultdict

    groups: dict[str, list] = defaultdict(list)
    for e in plan.include:
        groups[str(Path(e["path"]).with_suffix(""))].append(e)

    new_include: list = []
    new_dedup: list = list(plan.dedup_groups)
    emitted: set[str] = set()
    for e in plan.include:
        key = str(Path(e["path"]).with_suffix(""))
        if key in emitted:
            continue
        emitted.add(key)
        by_family: dict[str, list] = defaultdict(list)
        for m in groups[key]:
            by_family[_fmt_family(m["path"])].append(m)
        for members in by_family.values():
            keep = min(members, key=lambda m: _fmt_rank(m["path"]))
            new_include.append(keep)
            if len(members) > 1:
                new_dedup.append({
                    "keep": keep["path"],
                    "drop": [m["path"] for m in members if m["path"] != keep["path"]],
                    "reason": "format-variant of same document (same folder+stem+family); kept richest format",
                })
    return Plan(plan.scope, plan.corpus_root, plan.subtree, new_include,
                plan.exclude, new_dedup, plan.supersedes)

"""Stamp invariant metadata into atomic-markdown frontmatter.

platform/product/version/source_doc are known per source-doc at dispatch time and
are identical across a batch. The LLM is unreliable at echoing them, so fill them
in deterministically. By default only MISSING fields are added, preserving any
content-derived values the subagent wrote (content-trust).
"""
from __future__ import annotations
from pathlib import Path
import yaml as _yaml


def stamp_file(path: Path, fields: dict, only_missing: bool = True) -> list[str]:
    """Add/overwrite frontmatter fields in one .md. Returns the field names changed.
    Skips (returns []) if the file has no valid '---' frontmatter fence."""
    text = path.read_text()
    if not text.startswith("---"):
        return []
    parts = text.split("---", 2)
    if len(parts) < 3:
        return []
    _, fm, body = parts
    lines = fm.strip("\n").splitlines()
    present = {}
    for ln in lines:
        if ":" in ln:
            present[ln.split(":", 1)[0].strip()] = ln
    changed = []
    for key, val in fields.items():
        if val is None:
            continue
        if key in present and only_missing:
            continue
        # remove any existing line for key (overwrite case)
        lines = [ln for ln in lines if not ln.startswith(f"{key}:")]
        # insert after slug if present, else at top
        newline = f'{key}: {val}'
        if any(ln.startswith("slug:") for ln in lines):
            out = []
            for ln in lines:
                out.append(ln)
                if ln.startswith("slug:"):
                    out.append(newline)
            lines = out
        else:
            lines.insert(0, newline)
        changed.append(key)
    if changed:
        path.write_text("---\n" + "\n".join(lines) + "\n---" + body)
    return changed


def stamp_dir(atomic_dir: Path, fields: dict, only_missing: bool = True) -> dict:
    """Apply stamp_file to every *.md. Returns {filename: [changed fields]} for files changed."""
    result = {}
    for md in sorted(atomic_dir.glob("*.md")):
        ch = stamp_file(md, fields, only_missing=only_missing)
        if ch:
            result[md.name] = ch
    return result


_YAML_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "~"}


def _yaml_scalar(v):
    if v is None:
        return None
    s = str(v)
    try:
        float(s); return f'"{s}"'
    except (ValueError, TypeError):
        pass
    if s.lower() in _YAML_RESERVED:
        return f'"{s}"'
    return s


def stamp_from_plan(atomic_dir: Path, plan, only_missing: bool = True) -> dict:
    """Stamp invariant frontmatter fields into each .md from its matching plan include entry.

    Matches on the folder-qualified `slug` (unique per include), NOT the filename basename, many WMS docs share a basename across module folders, so basename matching would stamp the
    wrong metadata onto all but one of them."""
    from hiveprep.slugs import assign_slugs

    by_slug = {slug: e for slug, e in zip(assign_slugs(plan.include), plan.include)}
    changed: dict = {}
    for md in sorted(Path(atomic_dir).glob("*.md")):
        text = md.read_text()
        if not text.startswith("---"):
            continue
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        try:
            fm = _yaml.safe_load(parts[1]) or {}
        except _yaml.YAMLError:
            continue
        entry = by_slug.get(str(fm.get("slug", "")))
        if not entry:
            continue
        fields = {k: entry.get(k) for k in ("platform", "product", "version", "doc_type", "topic")}
        fields["source_doc"] = entry["path"]
        c = stamp_file(md, {k: _yaml_scalar(v) for k, v in fields.items()}, only_missing=only_missing)
        if c:
            changed[md.name] = c
    return changed

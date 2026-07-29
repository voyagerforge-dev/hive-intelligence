"""Load atomic markdown and slice it into a generatable functional area.

Slicing is by ``topic:`` frontmatter: the curation stage labels each document with a topic,
and the corpus profile groups those topics into functional areas. Running one area at a time
is what keeps a taxonomy call from having to span a whole corpus.

The area vocabulary is **not** in this module. It describes one corpus and ships with that
corpus; see ``hivegen.profile``.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from hivegen.profile import SubArea, load_profile, missing_profile_error

__all__ = [
    "Doc",
    "SubArea",
    "area_names",
    "frontmatter_topic",
    "load_area_local",
    "load_docs",
    "load_docs_local",
    "load_subarea_local",
    "subarea_names",
]


def area_names(profile=None) -> list[str]:
    return sorted((profile or load_profile()).areas)


def subarea_names(profile=None) -> list[str]:
    return sorted((profile or load_profile()).subareas)


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


def load_docs(s3, bucket: str, prefix: str, *,
              name_keywords: Iterable[str] | None = None) -> list[Doc]:
    """Read atomic markdown from object storage, optionally narrowed by filename keyword."""
    kw = tuple(k.lower() for k in name_keywords) if name_keywords else ()
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    out: list[Doc] = []
    for obj in resp.get("Contents", []):
        key = obj["Key"]
        if not key.endswith(".md"):
            continue
        if kw and not any(k in key.lower() for k in kw):
            continue
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        text = body.decode() if isinstance(body, bytes) else str(body)
        out.append(Doc(id=key, name=key, text=text))
    return out


def load_docs_local(root, *, topics: Iterable[str] | None = None,
                    name_include: Iterable[str] | None = None,
                    name_exclude: Iterable[str] | None = None) -> list[Doc]:
    """Read atomic markdown from a local directory.

    ``topics`` selects documents whose ``topic:`` frontmatter is in that set,
    case-insensitively. ``name_include`` and ``name_exclude`` narrow further by filename
    substring: a document is kept only if its filename contains an include keyword (when any
    are given) and none of the excludes. That pair is how a sub-slice carves one topic.

    With no filters at all, every document under ``root`` is returned.
    """
    root = Path(root)
    want = {t.strip().lower() for t in topics} if topics is not None else None
    inc = tuple(k.lower() for k in name_include) if name_include else ()
    exc = tuple(k.lower() for k in name_exclude) if name_exclude else ()
    out: list[Doc] = []
    for path in sorted(root.glob("*.md")):
        text = path.read_text()
        if want is not None and frontmatter_topic(text).lower() not in want:
            continue
        low = path.name.lower()
        if inc and not any(k in low for k in inc):
            continue
        if exc and any(k in low for k in exc):
            continue
        out.append(Doc(id=path.name, name=path.name, text=text))
    return out


def load_area_local(root, area: str, profile=None) -> list[Doc]:
    """Load the atomic docs for a named functional area, as defined by the corpus profile."""
    profile = profile or load_profile()
    if area not in profile.areas:
        if profile.is_empty:
            raise KeyError(missing_profile_error("functional areas", area))
        raise KeyError(f"unknown area '{area}'; {profile.path} defines: {sorted(profile.areas)}")
    return load_docs_local(root, topics=profile.areas[area])


def load_subarea_local(root, name: str, profile=None) -> list[Doc]:
    """Load the atomic docs for a named sub-slice, as defined by the corpus profile."""
    profile = profile or load_profile()
    if name not in profile.subareas:
        if profile.is_empty:
            raise KeyError(missing_profile_error("sub-areas", name))
        raise KeyError(
            f"unknown sub-area '{name}'; {profile.path} defines: {sorted(profile.subareas)}")
    sa = profile.subareas[name]
    return load_docs_local(root, topics=sa.topics,
                           name_include=sa.include or None,
                           name_exclude=sa.exclude or None)

"""The corpus profile, as far as hive-prep is concerned.

The same ``corpus-profile.yaml`` that ``hive-gen`` reads, but this package only needs one
section of it: the folder-name aliases that map a directory segment to a canonical product
code. The loader is deliberately duplicated rather than shared, because these two packages
are independently installable and neither should depend on the other for a schema this
small.

A missing profile is normal and not an error. Without one there is simply no product
aliasing, and folder segments contribute no product hint. Those hints supplement
classification rather than driving it, so their absence degrades quality slightly instead of
breaking a run.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

PROFILE_FILENAME = "corpus-profile.yaml"


def _candidates(explicit: str | None, corpus_root: str | None) -> list[Path]:
    out: list[Path] = []
    if explicit:
        out.append(Path(explicit))
    out.append(Path.cwd() / PROFILE_FILENAME)
    if corpus_root:
        out.append(Path(corpus_root) / PROFILE_FILENAME)
        out.append(Path(corpus_root).parent / PROFILE_FILENAME)
    return out


def load_product_aliases(explicit: str | None = None,
                         corpus_root: str | None = None) -> dict[str, str]:
    """Folder-segment alias to canonical product code, lower-cased keys.

    Returns an empty mapping when there is no profile, which disables product hinting.
    """
    if explicit is None:
        explicit = os.environ.get("CORPUS_PROFILE") or None
    if corpus_root is None:
        corpus_root = os.environ.get("CORPUS_ROOT") or None

    for path in _candidates(explicit, corpus_root):
        if not path.is_file():
            continue
        raw = yaml.safe_load(path.read_text()) or {}
        if not isinstance(raw, dict):
            raise TypeError(
                f"{path}: corpus profile must be a mapping, got {type(raw).__name__}")
        products = raw.get("products") or {}
        return {str(k).lower().strip(): str(v) for k, v in products.items()}
    return {}


def load_curation_vocabulary(explicit: str | None = None,
                             corpus_root: str | None = None) -> dict[str, list[str]]:
    """Values a curation plan may assign, from the profile's ``curation`` section.

    Returns ``{"products": [...], "platforms": [...]}``, empty when undeclared. Empty means
    the corresponding check is skipped: a validator holding a hardcoded vocabulary rejects
    every value that is valid in some other corpus, which fails closed on good data.
    """
    if explicit is None:
        explicit = os.environ.get("CORPUS_PROFILE") or None
    if corpus_root is None:
        corpus_root = os.environ.get("CORPUS_ROOT") or None

    for path in _candidates(explicit, corpus_root):
        if not path.is_file():
            continue
        raw = yaml.safe_load(path.read_text()) or {}
        if not isinstance(raw, dict):
            raise TypeError(
                f"{path}: corpus profile must be a mapping, got {type(raw).__name__}")
        cur = raw.get("curation") or {}
        return {
            "products": [str(x) for x in (cur.get("products") or [])],
            "platforms": [str(x) for x in (cur.get("platforms") or [])],
        }
    return {"products": [], "platforms": []}

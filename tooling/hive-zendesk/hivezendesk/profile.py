"""The corpus profile, as far as hive-zendesk is concerned.

The same ``corpus-profile.yaml`` the other packages read. This one needs the ``linking``
section: which product an entry belongs to by default, which words mark an entry as
belonging to some other product, and which corpus-specific words carry no signal.

All three are corpus vocabulary. Hardcoding them meant an entry from any other corpus was
filed under a product that did not exist there.

The loader is deliberately duplicated rather than shared: these packages are independently
installable, and each reads a disjoint section of the file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PROFILE_FILENAME = "corpus-profile.yaml"


@dataclass(frozen=True)
class LinkingProfile:
    #: The product an entry is filed under when nothing marks it as anything else.
    default_product: str = ""
    #: product -> marker words. A marker in the entry's own text permits that product.
    product_markers: dict[str, set[str]] = field(default_factory=dict)
    #: Corpus-specific words with no discriminating power, added to the generic stop list.
    extra_stopwords: set[str] = field(default_factory=set)
    path: Path | None = None


def _candidates(explicit: str | None) -> list[Path]:
    out: list[Path] = []
    if explicit:
        out.append(Path(explicit))
    out.append(Path.cwd() / PROFILE_FILENAME)
    return out


def load_linking_profile(explicit: str | None = None) -> LinkingProfile:
    if explicit is None:
        explicit = os.environ.get("CORPUS_PROFILE") or None

    for path in _candidates(explicit):
        if not path.is_file():
            continue
        raw = yaml.safe_load(path.read_text()) or {}
        if not isinstance(raw, dict):
            raise TypeError(
                f"{path}: corpus profile must be a mapping, got {type(raw).__name__}")
        link = raw.get("linking") or {}
        return LinkingProfile(
            default_product=str(link.get("default_product") or ""),
            product_markers={
                str(p): {str(m).lower() for m in (markers or [])}
                for p, markers in (link.get("product_markers") or {}).items()
            },
            extra_stopwords={str(w).lower() for w in (link.get("extra_stopwords") or [])},
            path=path,
        )
    return LinkingProfile()

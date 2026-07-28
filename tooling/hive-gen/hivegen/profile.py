"""The corpus profile: a corpus's domain vocabulary, as data rather than as code.

Hive's pipeline needs to know things that are true of *a* corpus and false of every other
one: which functional areas its documents fall into, which topic values the curation stage
assigned, which product names its folders use. That knowledge used to live in Python
dictionaries in this package, which meant pointing Hive at a different body of documents
required editing the product.

It now lives in one YAML file that ships with the corpus, because that is whose knowledge
it is.

Resolution order for the file:

1. the ``CORPUS_PROFILE`` setting, if set
2. ``corpus-profile.yaml`` in the current working directory
3. ``corpus-profile.yaml`` beside the atomic document directory

A missing profile is not an error at import time. It becomes an error only when something
asks for an area that no profile defines, and that error names the setting, because
"unknown area 'inbound'" is a much worse message than "no corpus profile found".

See ``corpus-profile.example.yaml`` at the repository root for the schema.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PROFILE_FILENAME = "corpus-profile.yaml"


@dataclass(frozen=True)
class SubArea:
    """A keyword sub-slice of one oversized topic.

    A document matches when its topic is in ``topics``, its filename contains one of
    ``include`` (or ``include`` is empty), and its filename contains none of ``exclude``.
    Sub-slices sharing a topic stay disjoint by each naming its own family in ``include``
    while the remainder slice excludes all the others.
    """

    topics: tuple[str, ...]
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True)
class CorpusProfile:
    areas: dict[str, tuple[str, ...]] = field(default_factory=dict)
    subareas: dict[str, SubArea] = field(default_factory=dict)
    guide_topics: dict[str, str] = field(default_factory=dict)
    retopic_bucket: str = ""
    products: dict[str, str] = field(default_factory=dict)
    #: Canonical facet values. Validators gate card frontmatter on these, so an empty set
    #: means "do not validate this facet" rather than "reject everything".
    card_products: tuple[str, ...] = ()
    #: Display titles for product facets, used when generating index pages.
    product_titles: dict[str, str] = field(default_factory=dict)
    #: Filename prefixes shared by most documents, stripped before a title is shown to a
    #: model. They carry no signal and crowd out the part of the name that does.
    filename_prefixes: tuple[str, ...] = ()
    path: Path | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.areas or self.subareas or self.guide_topics or self.products
                    or self.card_products)


def _candidates(explicit: str | None, atomic_dir: str | None) -> list[Path]:
    out: list[Path] = []
    if explicit:
        out.append(Path(explicit))
    out.append(Path.cwd() / PROFILE_FILENAME)
    if atomic_dir:
        out.append(Path(atomic_dir).parent / PROFILE_FILENAME)
    return out


def find_profile_path(explicit: str | None = None,
                      atomic_dir: str | None = None) -> Path | None:
    for p in _candidates(explicit, atomic_dir):
        if p.is_file():
            return p
    return None


def load_profile(explicit: str | None = None,
                 atomic_dir: str | None = None) -> CorpusProfile:
    """Load the corpus profile, or return an empty one if there is none to load."""
    if explicit is None:
        explicit = os.environ.get("CORPUS_PROFILE") or None
    if atomic_dir is None:
        atomic_dir = os.environ.get("ATOMIC_DIR") or None

    path = find_profile_path(explicit, atomic_dir)
    if path is None:
        return CorpusProfile()

    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise TypeError(f"{path}: corpus profile must be a mapping, got {type(raw).__name__}")

    areas = {str(k): tuple(v or ()) for k, v in (raw.get("areas") or {}).items()}

    subareas: dict[str, SubArea] = {}
    for name, spec in (raw.get("subareas") or {}).items():
        if not isinstance(spec, dict):
            raise ValueError(f"{path}: subarea '{name}' must be a mapping")
        if not spec.get("topics"):
            # A sub-area with no topics matches nothing, silently. Refuse it: a slice that
            # loads zero documents looks identical to a corpus that has none.
            raise ValueError(f"{path}: subarea '{name}' must name at least one topic")
        subareas[str(name)] = SubArea(
            topics=tuple(spec.get("topics") or ()),
            include=tuple(spec.get("include") or ()),
            exclude=tuple(spec.get("exclude") or ()),
        )

    return CorpusProfile(
        areas=areas,
        subareas=subareas,
        guide_topics={str(k): str(v) for k, v in (raw.get("guide_topics") or {}).items()},
        retopic_bucket=str(raw.get("retopic_bucket") or ""),
        products={str(k): str(v) for k, v in (raw.get("products") or {}).items()},
        card_products=tuple(str(x) for x in ((raw.get("facets") or {}).get("product") or ())),
        product_titles={str(k): str(v)
                        for k, v in ((raw.get("facets") or {}).get("titles") or {}).items()},
        filename_prefixes=tuple(str(x) for x in (raw.get("filename_prefixes") or ())),
        path=path,
    )


def missing_profile_error(what: str, name: str) -> str:
    """The message for 'you asked for X and there is no vocabulary defining it'."""
    return (
        f"no corpus profile found, so no {what} are defined (asked for '{name}').\n"
        f"A corpus profile describes one corpus's domain vocabulary and ships with that "
        f"corpus, not with Hive.\n"
        f"Set CORPUS_PROFILE, or put {PROFILE_FILENAME} in the working directory or beside "
        f"ATOMIC_DIR.\n"
        f"See corpus-profile.example.yaml for the schema."
    )

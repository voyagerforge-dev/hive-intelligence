"""Locating the corpus.

The corpus became a separate repository on 2026-08-11. Nothing about where it sits on
disk follows from where this code is installed, so every tool that reads it is *told*,
through its own ``config.py``, and refuses when it has not been.

This module exists because the alternative was tried and failed silently. Code that used
to reach sideways inside one tree kept walking up the directory chain after the split and
landed in the *engine* repository, which has no ``concepts/`` and no approved taxonomies.
Nothing raised: :func:`pathlib.Path.rglob` over a directory that is not there yields
nothing and reports nothing, so the tools carried on over an empty corpus and produced
confident, wrong output. Directory arithmetic from ``__file__`` is fine for finding a
package's own files and is never right for finding another repository's.

The check is deliberately "set, and a directory", not "looks like a corpus". A corpus that
has not been generated yet legitimately contains almost nothing, and a heuristic that
rejects it would replace one wrong answer with another.
"""
from __future__ import annotations

from pathlib import Path

_WHY_NO_DEFAULT = (
    "The corpus is a separate repository from the engine, and nothing about where it sits "
    "on disk follows from where this code is installed. There is no default worth guessing: "
    "a guess resolves to a directory that exists, is not yours, and holds nothing, which "
    "reads exactly like a corpus with nothing in it."
)


def require_dir(value: str, *, setting: str, what: str) -> Path:
    """Return ``value`` as an existing directory, or exit naming the setting that is wrong.

    Refusing up front is the whole point: it is the difference between a run that says why
    it stopped and a run that reports success over zero cards.
    """
    if not str(value).strip():
        raise SystemExit(
            f"{setting} is not set, so there is no way to find {what}.\n{_WHY_NO_DEFAULT}")
    path = Path(value).expanduser()
    if not path.is_dir():
        raise SystemExit(
            f"{setting}={value} is not a directory (resolved to {path.resolve()}), "
            f"so {what} cannot be read.\n{_WHY_NO_DEFAULT}")
    return path

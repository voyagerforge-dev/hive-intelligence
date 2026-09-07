"""Lint OKF client-memory cards. Structural errors (exit 1): bad client/product, dangling
related target, bad supersedes, status inconsistency. Also emits conflict CANDIDATES (same
client + shared related/tag) for the LLM conflict scorer to judge, candidates do NOT fail.
Usage: hivegen-memory-lint <clients_dir> <concepts_dir>"""
import argparse
import glob
import os

import yaml

from hivegen.corpus import require_dir
from hivegen.profile import load_profile

# Valid `product:` facet values, from the corpus profile. An empty set means the profile
# does not declare them, and the check is skipped: a hardcoded list rejects every product
# that exists in some other corpus, which is a validator that fails closed on valid data.
ALLOWED_PRODUCTS = set(load_profile().card_products)


def _fm(p):
    with open(p) as _fh:
        _text = _fh.read()
    parts = _text.split("---", 2)
    return yaml.safe_load(parts[1]) if len(parts) >= 3 else {}


# The repository-relative prefix client memory lives under. Card ids are built from it
# here, and `pr_conflict_gate.pr_touches_memory` decides whether a PR needs scoring by
# matching it. Those are the same fact and must not be two strings: pr_conflict_gate.py
# used to hardcode `knowledge/okf/clients/`, a stale monorepo-era prefix that never
# matches the `clients/` corpora this tooling runs against, so the gate matched nothing
# and posted `okf/memory-conflict` success on every memory PR without ever scoring one.
# A gate that reports green on every memory PR is worse than one switched off, because
# the green is evidence of nothing and reads as evidence of something. Import this
# constant instead of restating the string.
CLIENTS_PREFIX = "clients/"


def _memories(clients_dir):
    out = {}
    for p in glob.glob(f"{clients_dir}/**/*.md", recursive=True):
        if os.path.basename(p) in ("index.md", "log.md"):
            continue
        rel = os.path.relpath(p, clients_dir)
        parts = rel[:-3].split(os.sep)
        if len(parts) < 3 or parts[1] != "memory":
            continue
        out[CLIENTS_PREFIX + "/".join(parts)] = _fm(p) or {}
    return out


def _concept_ids(concepts_dir):
    ids = set()
    for p in glob.glob(f"{concepts_dir}/**/*.md", recursive=True):
        if os.path.basename(p) in ("index.md", "log.md"):
            continue
        ids.add(os.path.relpath(p, concepts_dir)[:-3])
    return ids


def _as_list(v):
    if v is None:
        return []
    return [v] if isinstance(v, str) else list(v)


def lint(clients_dir, concepts_dir):
    mems = _memories(str(clients_dir))
    concept_ids = _concept_ids(str(concepts_dir))
    errors = []
    superseded = set()
    for cid, fm in mems.items():
        if ALLOWED_PRODUCTS and fm.get("product") not in ALLOWED_PRODUCTS:
            errors.append(f"{cid}: bad or missing product '{fm.get('product')}'")
        for rid in _as_list(fm.get("related")):
            if rid not in concept_ids:
                errors.append(f"{cid}: dangling related target '{rid}'")
        for sid in _as_list(fm.get("supersedes")):
            sup = mems.get(sid)
            if sup is None:
                errors.append(f"{cid}: supersedes unknown memory '{sid}'")
            elif sup.get("client") != fm.get("client"):
                errors.append(f"{cid}: supersedes a different client's memory '{sid}'")
            elif fm.get("status") == "approved":
                superseded.add(sid)
    for sid in superseded:
        if mems.get(sid, {}).get("status") == "approved":
            errors.append(f"{sid}: superseded by an active memory but still status: approved")
    # conflict candidates over ACTIVE memories, grouped by client
    active = {cid: fm for cid, fm in mems.items()
              if fm.get("status") == "approved" and cid not in superseded}
    by_client = {}
    for cid, fm in active.items():
        by_client.setdefault(fm.get("client"), []).append((cid, fm))
    candidates = []
    for items in by_client.values():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                (a, fa), (b, fb) = items[i], items[j]
                shared_rel = set(_as_list(fa.get("related"))) & set(_as_list(fb.get("related")))
                shared_tag = set(_as_list(fa.get("tags"))) & set(_as_list(fb.get("tags")))
                if shared_rel or shared_tag:
                    candidates.append((a, b))
    return errors, candidates


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="hivegen-memory-lint",
        description="Lint client-memory cards and list same-client conflict candidates.")
    ap.add_argument("clients_dir", help="the corpus clients/ tree")
    ap.add_argument("concepts_dir", help="the corpus concepts/ tree the memories relate to")
    args = ap.parse_args(argv)
    clients = require_dir(args.clients_dir, setting="clients_dir",
                          what="the memory cards to lint")
    concepts = require_dir(args.concepts_dir, setting="concepts_dir",
                           what="the concepts the memories relate to")
    errs, cands = lint(clients, concepts)
    for a, b in cands:
        print(f"CANDIDATE {a} <> {b} (same client, shared subject), score for conflict")
    for e in errs:
        print(f"ERROR {e}")
    print(f"memory_lint: {len(errs)} errors, {len(cands)} conflict candidates")
    return 1 if errs else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

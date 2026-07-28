"""Lint OKF client-memory cards. Structural errors (exit 1): bad client/product, dangling
related target, bad supersedes, status inconsistency. Also emits conflict CANDIDATES (same
client + shared related/tag) for the LLM conflict scorer to judge, candidates do NOT fail.
Usage: python scripts/memory_lint.py <clients_dir> <concepts_dir>"""
import glob
import os
import sys

import yaml

from hivegen.profile import load_profile

# Valid `product:` facet values, from the corpus profile. An empty set means the profile
# does not declare them, and the check is skipped: a hardcoded list rejects every product
# that exists in some other corpus, which is a validator that fails closed on valid data.
ALLOWED_PRODUCTS = set(load_profile().card_products)


def _fm(p):
    parts = open(p).read().split("---", 2)
    return yaml.safe_load(parts[1]) if len(parts) >= 3 else {}


def _memories(clients_dir):
    out = {}
    for p in glob.glob(f"{clients_dir}/**/*.md", recursive=True):
        if os.path.basename(p) in ("index.md", "log.md"):
            continue
        rel = os.path.relpath(p, clients_dir)
        parts = rel[:-3].split(os.sep)
        if len(parts) < 3 or parts[1] != "memory":
            continue
        out["clients/" + "/".join(parts)] = _fm(p) or {}
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


if __name__ == "__main__":  # pragma: no cover
    errs, cands = lint(sys.argv[1], sys.argv[2])
    for a, b in cands:
        print(f"CANDIDATE {a} <> {b} (same client, shared subject), score for conflict")
    for e in errs:
        print(f"ERROR {e}")
    print(f"memory_lint: {len(errs)} errors, {len(cands)} conflict candidates")
    sys.exit(1 if errs else 0)

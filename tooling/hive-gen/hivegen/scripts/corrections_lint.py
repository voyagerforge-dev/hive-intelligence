"""Lint OKF correction cards. Errors (exit 1): dangling corrects target, bad supersedes,
status inconsistency. Warning: >1 active correction on one concept (potential conflict).
Usage: hivegen-corrections-lint <concepts_dir>"""
import argparse
import glob
import os

import yaml

from hivegen.corpus import require_dir


def _fm(p):
    with open(p) as _fh:
        _text = _fh.read()
    parts = _text.split("---", 2)
    return yaml.safe_load(parts[1]) if len(parts) >= 3 else {}


def lint(concepts_dir):
    concepts_dir = str(concepts_dir)
    cards = {}  # id -> fm
    for p in glob.glob(f"{concepts_dir}/**/*.md", recursive=True):
        if os.path.basename(p) in ("index.md", "log.md"):
            continue
        cid = os.path.relpath(p, concepts_dir)[:-3]
        cards[cid] = _fm(p) or {}
    corrections = {cid: fm for cid, fm in cards.items() if fm.get("type") == "correction"}
    errors, warnings = [], []
    active_by_target = {}
    superseded_targets = set()
    for cid, fm in corrections.items():
        tgt = fm.get("corrects")
        if tgt not in cards or cards.get(tgt, {}).get("type") == "correction":
            errors.append(f"{cid}: dangling corrects target '{tgt}'")
        sup = fm.get("supersedes") or []
        if isinstance(sup, str):
            sup = [sup]
        for sid in sup:
            if sid not in corrections:
                errors.append(f"{cid}: supersedes unknown correction '{sid}'")
            elif fm.get("status") == "approved":
                superseded_targets.add(sid)
        if fm.get("status") == "approved" and tgt in cards:
            active_by_target.setdefault(tgt, []).append(cid)
    for sid in superseded_targets:
        if corrections.get(sid, {}).get("status") == "approved":
            errors.append(f"{sid}: superseded by an active correction but still status: approved")
    for tgt, ids in active_by_target.items():
        live = [i for i in ids if i not in superseded_targets]
        if len(live) > 1:
            warnings.append(f"{tgt}: {len(live)} active corrections ({', '.join(live)}), review for conflict")
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="hivegen-corrections-lint",
        description="Lint correction cards for dangling targets, bad supersedes and conflicts.")
    ap.add_argument("concepts_dir", help="the corpus concepts/ tree")
    args = ap.parse_args(argv)
    errs, warns = lint(require_dir(args.concepts_dir, setting="concepts_dir",
                                   what="the correction cards to lint"))
    for w in warns:
        print(f"WARN  {w}")
    for e in errs:
        print(f"ERROR {e}")
    print(f"corrections_lint: {len(errs)} errors, {len(warns)} warnings")
    return 1 if errs else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

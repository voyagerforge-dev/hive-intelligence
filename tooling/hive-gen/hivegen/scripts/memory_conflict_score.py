"""LLM conflict-probability gate over memory_lint's candidate pairs (CI/authoring-side only,
never the serving connector). For each same-client candidate pair, ask an injected ChatLLM
whether the two memories make mutually incompatible claims; a high probability blocks the PR.
Fail-safe: any LLM error/unparseable reply scores 1.0 (block, human review).
Usage: hivegen-memory-conflict-score <clients_dir> <concepts_dir>"""
from __future__ import annotations

import argparse

from hivegen.llm import extract_json
from hivegen.scripts import gateway_llm, memory_lint

_SYS = (
    "You judge whether two client-memory notes about the SAME client CONFLICT, i.e. make "
    "mutually incompatible claims about how that client's system behaves. Overlapping topic is "
    "NOT conflict; only contradiction is. Reply with ONLY "
    '{"probability": <0..1>, "rationale": "<short>"}.'
)


def _text(fm: dict) -> str:
    return f"{fm.get('title', '')}: {fm.get('memory', fm.get('description', ''))}"


def score_pair(fa: dict, fb: dict, llm) -> dict:
    user = f"MEMORY A:\n{_text(fa)}\n\nMEMORY B:\n{_text(fb)}"
    try:
        data = extract_json(llm.complete(_SYS, user) or "")
    except Exception:  # noqa: BLE001 - any scoring failure must fall through to fail-safe block
        data = None
    if not data or "probability" not in data:
        return {"probability": 1.0, "rationale": "unscored, fail-safe block"}
    try:
        p = float(data["probability"])
    except (TypeError, ValueError):
        return {"probability": 1.0, "rationale": "unscored, fail-safe block"}
    return {"probability": max(0.0, min(1.0, p)),
            "rationale": str(data.get("rationale", ""))}


def gate(candidates, memories, llm, *, block_threshold=0.6, warn_threshold=0.3,
         llm_factory=None):
    blocking, review = [], []
    for a, b in candidates:
        pair_llm = llm_factory((a, b)) if llm_factory else llm
        r = score_pair(memories.get(a, {}), memories.get(b, {}), pair_llm)
        if r["probability"] >= block_threshold:
            blocking.append((a, b))
        elif r["probability"] >= warn_threshold:
            review.append((a, b))
    return blocking, review


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="hivegen-memory-conflict-score",
        description="Score memory_lint's same-client candidate pairs for contradiction. "
                    "With no gateway configured it prints the candidate pairs for a human "
                    "to read and does not fail the step.")
    ap.add_argument("clients_dir", help="the corpus clients/ tree")
    ap.add_argument("concepts_dir", help="the corpus concepts/ tree the memories relate to")
    args = ap.parse_args(argv)
    _errors, candidates = memory_lint.lint(args.clients_dir, args.concepts_dir)
    if not candidates:
        print("memory_conflict_score: 0 candidates")
        return 0
    mems = memory_lint._memories(args.clients_dir)
    llm = gateway_llm()
    if llm is None:
        print(f"memory_conflict_score: {len(candidates)} candidate(s), no LLM key set, ADVISORY only:")
        for a, b in candidates:
            print(f"  CANDIDATE {a} <> {b}")
        return 0
    blocking, review = gate(candidates, mems, llm)
    for a, b in review:
        print(f"REVIEW {a} <> {b}, human check")
    for a, b in blocking:
        print(f"CONFLICT {a} <> {b}, resolve (supersede/reconcile/reject) before merge")
    return 1 if blocking else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

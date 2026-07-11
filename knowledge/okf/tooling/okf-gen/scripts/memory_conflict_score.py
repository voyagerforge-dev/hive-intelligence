"""LLM conflict-probability gate over memory_lint's candidate pairs (CI/authoring-side only —
never the serving connector). For each same-client candidate pair, ask an injected ChatLLM
whether the two memories make mutually incompatible claims; a high probability blocks the PR.
Fail-safe: any LLM error/unparseable reply scores 1.0 (block, human review)."""
from __future__ import annotations

from okfgen.llm import extract_json

_SYS = (
    "You judge whether two client-memory notes about the SAME client CONFLICT — i.e. make "
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
    except Exception:
        data = None
    if not data or "probability" not in data:
        return {"probability": 1.0, "rationale": "unscored — fail-safe block"}
    try:
        p = float(data["probability"])
    except (TypeError, ValueError):
        return {"probability": 1.0, "rationale": "unscored — fail-safe block"}
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


if __name__ == "__main__":  # pragma: no cover
    import importlib.util
    import os
    import sys
    from pathlib import Path

    clients_dir, concepts_dir = sys.argv[1], sys.argv[2]
    _ml = importlib.util.spec_from_file_location("memory_lint", Path(__file__).with_name("memory_lint.py"))
    ml = importlib.util.module_from_spec(_ml)
    _ml.loader.exec_module(ml)
    _errors, candidates = ml.lint(clients_dir, concepts_dir)
    if not candidates:
        print("memory_conflict_score: 0 candidates")
        sys.exit(0)
    mems = ml._memories(clients_dir)
    key = os.environ.get("BIFROST_API_KEY")
    base = os.environ.get("BIFROST_BASE")
    if not key or not base:
        print(f"memory_conflict_score: {len(candidates)} candidate(s), no LLM key set — ADVISORY only:")
        for a, b in candidates:
            print(f"  CANDIDATE {a} <> {b}")
        sys.exit(0)
    from okfgen.llm import BifrostChat
    llm = BifrostChat(base, key, os.environ.get("CONFLICT_MODEL", "minimax-m3"))
    blocking, review = gate(candidates, mems, llm)
    for a, b in review:
        print(f"REVIEW {a} <> {b} — human check")
    for a, b in blocking:
        print(f"CONFLICT {a} <> {b} — resolve (supersede/reconcile/reject) before merge")
    sys.exit(1 if blocking else 0)

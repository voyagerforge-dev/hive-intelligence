"""Orchestration core for the memory-conflict PR gate (used by the Windmill runnable
f/example/okf/memory_conflict_gate). Composes the tested memory_lint + memory_conflict_score
over a checked-out PR tree and turns the verdict into a GitHub commit-status payload.
Pure/testable: the LLM and all I/O are injected by the caller."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_CONTEXT = "okf/memory-conflict"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pr_touches_memory(changed_files) -> bool:
    return any(
        f.startswith("knowledge/okf/clients/") and "/memory/" in f and f.endswith(".md")
        for f in changed_files
    )


def score_tree(clients_dir, concepts_dir, llm):
    """(blocking, review) id-pairs for same-client memory conflicts in a checked-out tree."""
    lint = _load("memory_lint")
    scorer = _load("memory_conflict_score")
    _errors, candidates = lint.lint(clients_dir, concepts_dir)
    if not candidates:
        return [], []
    memories = lint._memories(str(clients_dir))
    return scorer.gate(candidates, memories, llm)


def _pairs(items) -> str:
    return ", ".join(f"{a} <> {b}" for a, b in items)


def verdict_to_status(blocking, review) -> dict:
    if blocking:
        desc = f"conflict: {_pairs(blocking)} - resolve (supersede/reconcile/reject)"
        return {"context": _CONTEXT, "state": "failure", "description": desc[:140]}
    if review:
        desc = f"possible conflict (review): {_pairs(review)} - confirm or supersede"
        return {"context": _CONTEXT, "state": "failure", "description": desc[:140]}
    return {"context": _CONTEXT, "state": "success",
            "description": "no same-client memory conflict"}

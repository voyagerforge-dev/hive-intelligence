"""Orchestration core for the memory-conflict PR gate (invoked by a Windmill runnable that
lives with the deployment). Composes the tested memory_lint + memory_conflict_score
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
    """Whether a PR changes a client memory card, and therefore needs scoring.

    The prefix comes from `memory_lint`, the module that builds card ids from it: import
    the fact, do not restate it. Restating it as a literal here is what broke this gate
    before: it hardcoded `knowledge/okf/clients/`, a stale monorepo-era prefix that never
    matches the `clients/` corpora this tooling runs against, so the gate matched nothing
    and posted `okf/memory-conflict` success on every memory PR without ever scoring one.
    """
    lint = _load("memory_lint")
    return any(
        f.startswith(lint.CLIENTS_PREFIX) and "/memory/" in f and f.endswith(".md")
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

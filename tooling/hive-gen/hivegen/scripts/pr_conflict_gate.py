"""Orchestration core for the memory-conflict PR gate. Composes the tested memory_lint +
memory_conflict_score over a checked-out PR tree and turns the verdict into a GitHub
commit-status payload. The three functions are pure/testable: the LLM and all I/O are
injected by the caller, which is how the corpus repository's own gate uses them.

`main` is the same composition made runnable for a caller that has no glue of its own; it
builds the LLM from the environment and prints the payload as JSON. Its `--changed-file`
values and its `clients_dir` must share a base: run it from the directory the changed paths
are relative to, which for `git diff --name-only` output is the repository root.
Usage: hivegen-pr-conflict-gate --changed-file PATH ... <clients_dir> <concepts_dir>"""
from __future__ import annotations

import argparse
import json
import os

from hivegen.scripts import gateway_llm, memory_conflict_score, memory_lint

_CONTEXT = "okf/memory-conflict"


def pr_touches_memory(changed_files, memory_prefix=memory_lint.CLIENTS_PREFIX) -> bool:
    """Whether a PR changes a client memory card, and therefore needs scoring.

    The default prefix comes from `memory_lint`, the module that builds card ids from it:
    import the fact, do not restate it. Restating it as a literal here is what broke this
    gate before: it hardcoded `knowledge/okf/clients/`, a stale monorepo-era prefix that
    never matches the `clients/` corpora this tooling runs against, so the gate matched
    nothing and posted `okf/memory-conflict` success on every memory PR without ever
    scoring one.

    `memory_prefix` overrides it for a corpus that does not sit at the repository root, and
    is a DIFFERENT fact from `memory_lint.CLIENTS_PREFIX`: that one stamps card ids, which
    stay `clients/...` whatever the tree is called on disk, while this one only decides
    whether a changed path is a memory card. Do not collapse the two back together. The
    default is the case where they coincide, which is the corpus-at-the-root layout the
    corpus repository calls this with.
    """
    return any(
        f.startswith(memory_prefix) and "/memory/" in f and f.endswith(".md")
        for f in changed_files
    )


def changed_path_prefix(clients_dir) -> str:
    """The prefix `clients_dir`'s memory cards carry in `--changed-file` values.

    Changed paths come from `git diff --name-only`, so they are relative to the repository
    root, and the gate is run from there. A `clients_dir` outside that base cannot be
    compared with them at all, so it is refused rather than answered: the gate silently
    matching nothing is how it posts an authoritative green over a memory change no one
    scored.
    """
    rel = os.path.relpath(os.path.abspath(clients_dir), os.getcwd())
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        raise SystemExit(
            f"{clients_dir} is outside the working directory {os.getcwd()}, so no "
            "--changed-file path can name a card inside it. Run this from the directory "
            "the changed paths are relative to, which for `git diff --name-only` output "
            "is the repository root.")
    return "" if rel == os.curdir else rel.replace(os.sep, "/") + "/"


def score_tree(clients_dir, concepts_dir, llm):
    """(blocking, review) id-pairs for same-client memory conflicts in a checked-out tree."""
    _errors, candidates = memory_lint.lint(clients_dir, concepts_dir)
    if not candidates:
        return [], []
    memories = memory_lint._memories(str(clients_dir))
    return memory_conflict_score.gate(candidates, memories, llm)


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="hivegen-pr-conflict-gate",
        description="Decide whether a pull request's changed files touch client memory, "
                    "score the tree if they do, and print the commit-status payload.")
    ap.add_argument("clients_dir",
                    help="the corpus clients/ tree, as a path under the directory this is "
                         "run from")
    ap.add_argument("concepts_dir", help="the corpus concepts/ tree the memories relate to")
    ap.add_argument("--changed-file", action="append", default=[], metavar="PATH",
                    help="a path the pull request changed, relative to the directory this "
                         "is run from (`git diff --name-only` output, run from the "
                         "repository root); repeat it once per path")
    args = ap.parse_args(argv)

    if not args.changed_file:
        raise SystemExit(
            "No changed files were supplied: pass --changed-file PATH once per path the "
            "pull request changed. Refusing to report a verdict on a changeset nobody named.")

    if not pr_touches_memory(args.changed_file, changed_path_prefix(args.clients_dir)):
        print(json.dumps({"context": _CONTEXT, "state": "success",
                          "description": "no client memory card changed"}))
        return 0

    # Refuse rather than fall back to an unconfigured gateway. The scorer fails SAFE - an
    # unparseable reply scores 1.0 and blocks - so scoring without a gateway would block the
    # pull request with a verdict nothing measured, which reads exactly like a real conflict.
    llm = gateway_llm()
    if llm is None:
        raise SystemExit(
            "BIFROST_BASE and BIFROST_API_KEY must be set to score a memory change. "
            "Refusing to report a verdict without having scored anything.")

    status = verdict_to_status(*score_tree(args.clients_dir, args.concepts_dir, llm))
    print(json.dumps(status))
    return 0 if status["state"] == "success" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

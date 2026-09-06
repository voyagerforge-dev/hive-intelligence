"""DEPRECATED, and kept only for callers that still invoke this path.

The implementation is `hivegen.scripts.pr_conflict_gate`, published as the
`hivegen-pr-conflict-gate` console script from vf-hive-gen 0.7.0. A corpus workflow reading
this file off a hand-seeded engine checkout keeps working until it switches to that
command, at which point this shim goes.
"""
from hivegen.scripts.pr_conflict_gate import (  # noqa: F401
    main,
    pr_touches_memory,
    score_tree,
    verdict_to_status,
)

if __name__ == "__main__":
    raise SystemExit(main())

"""DEPRECATED, and kept only for callers that still invoke this path.

The implementation is `hivegen.scripts.memory_lint`, published as the
`hivegen-memory-lint` console script from vf-hive-gen 0.7.0. A corpus workflow reading
this file off a hand-seeded engine checkout keeps working until it switches to that
command, at which point this shim goes.
"""
from hivegen.scripts.memory_lint import main

if __name__ == "__main__":
    raise SystemExit(main())

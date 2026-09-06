"""DEPRECATED, and kept only for callers that still invoke this path.

The implementation is `hivegen.scripts.index_generate`, published as the
`hivegen-index-generate` console script from vf-hive-gen 0.7.0. A corpus workflow reading
this file off a hand-seeded engine checkout keeps working until it switches to that
command, at which point this shim goes.
"""
from hivegen.scripts.index_generate import main

if __name__ == "__main__":
    raise SystemExit(main())

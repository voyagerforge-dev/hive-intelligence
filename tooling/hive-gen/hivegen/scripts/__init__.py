"""The command line over hive-gen's card machinery, as installable code.

Every module here is a thin `main()` around functions that live elsewhere in `hivegen`:
what decides whether two memories conflict, or which `product:` values are valid, is the
library, and these only read argv and print. Each one is declared in `[project.scripts]`
and reaches an installed environment as a `hivegen-`prefixed console script, so a consumer
that pins `vf-hive-gen` gets the commands and not only the library.

They became installable at 0.7.0; `docs/reference/hive-gen.md` records what the wheel carried
before that and what a caller still reading an old `tooling/hive-gen/scripts/` path does now.

Adding a module here puts it in the wheel automatically; it does NOT become a command until
`[project.scripts]` names it. `tests/test_console_scripts.py` holds the two halves of that
together: every PUBLIC module here must be declared, and every declared command must
resolve out of the built wheel. A module whose name starts with an underscore is a private
helper and is expected to have no command; that is where shared glue goes, as `_gateway`
does for the conflict-scoring gateway two commands read.
"""

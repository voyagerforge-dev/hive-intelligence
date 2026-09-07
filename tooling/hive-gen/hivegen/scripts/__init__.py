"""The command line over hive-gen's card machinery, as installable code.

Every module here is a thin `main()` around functions that live elsewhere in `hivegen`:
what decides whether two memories conflict, or which `product:` values are valid, is the
library, and these only read argv and print. Each one is declared in `[project.scripts]`
and reaches an installed environment as a `hivegen-`prefixed console script, so a consumer
that pins `vf-hive-gen` gets the commands and not only the library.

Until 0.7.0 they did not. The wheel shipped `packages = ["hivegen"]` and these files sat in
a `scripts/` directory beside it that no artifact carried, so four workflows in the corpus
repository read them off a hand-seeded checkout on a host while importing the pinned
`hivegen` underneath - the wrapper and the logic it wrapped came from different places, and
only one of them was a version anything asserted. From 0.7.0 the commands are the only
supported entry point; the old `tooling/hive-gen/scripts/` paths for these eight are gone.

Adding a module here puts it in the wheel automatically; it does NOT become a command until
`[project.scripts]` names it. `tests/test_console_scripts.py` holds the two halves of that
together: every PUBLIC module here must be declared, and every declared command must
resolve out of the built wheel. A module whose name starts with an underscore is a private
helper and is expected to have no command; that is where shared glue goes, as `_gateway`
does for the conflict-scoring gateway two commands read.
"""

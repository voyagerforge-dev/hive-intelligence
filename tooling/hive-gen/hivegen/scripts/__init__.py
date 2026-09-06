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
`[project.scripts]` names it, and `tests/test_console_scripts.py` fails on a name declared
in one place and not the other. Shared glue therefore lives HERE rather than in a module of
its own, which that test would demand a command over.
"""
from __future__ import annotations

import os


def gateway_llm():
    """The conflict-scoring gateway from the environment, or None when it is not configured.

    One definition because two commands must agree on it: `hivegen-memory-conflict-score`
    and `hivegen-pr-conflict-gate` both score with it, and the scorer fails SAFE, so a
    default model updated in one copy and not the other would retire the model under one
    command and turn every candidate pair into a blocking verdict nothing measured. What an
    absent gateway MEANS stays with each caller - the scorer is advisory, the gate refuses.
    """
    base = os.environ.get("BIFROST_BASE")
    key = os.environ.get("BIFROST_API_KEY")
    if not base or not key:
        return None
    from hivegen.llm import BifrostChat
    return BifrostChat(base, key, os.environ.get("CONFLICT_MODEL", "minimax/minimax-m3"))

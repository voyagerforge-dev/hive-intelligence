"""The set this repository releases, as the proof scripts see it.

The set is stated once, in `tools/released-packages.sh`. The shell scripts source it; the
scripts here cannot, because they run inside the clean container where only /proof/*.py and
/corpus exist, so the harness that starts them passes it in as `RELEASED_PACKAGES` (the same
names, space separated). Deriving it beats restating it: a distribution added to the released
set is built into `dist/` and uploaded from there, so a proof that still checks the previous
set would stay green while an unproven wheel went to PyPI, which is irreversible.

Unset or empty refuses, naming the variable, exactly as the packages themselves do with a
corpus path. A default here would check the wrong set silently, which is worse than stopping.
"""
from __future__ import annotations

import os

REFUSAL = (
    "RELEASED_PACKAGES is not set. It is the released set, stated once in "
    "tools/released-packages.sh, and this script derives everything it checks from it. Run "
    "it as: . tools/released-packages.sh && "
    'RELEASED_PACKAGES="${RELEASED_PACKAGES[*]}" <this command>'
)


def released_packages() -> list[str]:
    """The tooling directory names, in the order they are released."""
    names = os.environ.get("RELEASED_PACKAGES", "").split()
    if not names:
        raise SystemExit(REFUSAL)
    return names


def distributions() -> dict[str, str]:
    """Distribution name -> the module it installs, for every released package.

    Both follow from the directory name by convention: `hive-gen` ships as `vf-hive-gen` and
    imports as `hivegen`. tools/build-release.sh derives the distribution name the same way
    and checks it against each wheel's recorded metadata Name, which is what keeps the
    convention true rather than merely assumed.
    """
    return {"vf-" + name: name.replace("-", "") for name in released_packages()}

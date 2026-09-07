#!/usr/bin/env python3
"""Read pip's own install report and say where each vf-hive distribution actually came from.

    . tools/released-packages.sh && RELEASED_PACKAGES="${RELEASED_PACKAGES[*]}" \\
        EXPECT_SCHEME=file tools/provenance.py <the --report json pip wrote>

Run against the install that is about to be believed: by tools/clean-install-inside.sh in the
clean container, and by the release workflow's install job. Both name the built wheel FILES
rather than `vf-name==version`, because a requirement pip can also satisfy from the index
smoke-tests the published copy once that version exists. Checking pip's record beats checking
our intent: it is the same question everywhere ("did these come from the local directory,
or from PyPI?") and it stays true after the names exist on an index, which an "it is on no
index" assertion would not.
"""
from __future__ import annotations

import json
import os
import sys

from released import distributions

REFUSAL = (
    "EXPECT_SCHEME is not set. It is where these distributions are supposed to have come "
    "from, and there is no default because the answer differs per run: `file` for an install "
    "off a local wheel file, `https` for one off the index. Run it as: "
    "EXPECT_SCHEME=file <this command>"
)


def main() -> int:
    # Before the argument check, so a run that is missing both is told about the variable:
    # the report path is visible in the command that was typed, and this is not.
    want = os.environ.get("EXPECT_SCHEME", "").strip()
    if not want:
        raise SystemExit(REFUSAL)
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    # Before the report is opened, so an unset released set is refused by name rather than
    # surfacing later as something else. It comes from tools/released-packages.sh and never
    # from a count written here: a sixth distribution the install never requested would
    # otherwise satisfy a literal 5.
    wanted = set(distributions())
    with open(sys.argv[1]) as fh:
        report = json.load(fh)
    ours = [i for i in report.get("install", []) if i["metadata"]["name"] in wanted]
    bad = []
    for item in sorted(ours, key=lambda i: i["metadata"]["name"]):
        name = item["metadata"]["name"]
        url = item.get("download_info", {}).get("url", "")
        print(f"    {name}  <-  {url}")
        if not url.startswith(want + "://"):
            bad.append(f"{name} came from {url!r}, expected a {want}:// URL")
    missing = sorted(wanted - {i["metadata"]["name"] for i in ours})
    if missing:
        bad.append(f"pip installed {len(ours)} of the {len(wanted)} released distributions; "
                   f"never installed: {', '.join(missing)}")
    if bad:
        print("\n  PROVENANCE FAILED:", file=sys.stderr)
        for b in bad:
            print("    - " + b, file=sys.stderr)
        return 1
    print(f"    all {len(wanted)} resolved from {want}:// as intended")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

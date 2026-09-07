#!/usr/bin/env python3
"""Report whether each released distribution is resolvable on PyPI right now.

Informational on purpose. A name answers 404 until its distribution has published and 200
afterwards, and they need not get there together - a release can legitimately be partial - so
asserting either way would give a check that starts failing on the day the work succeeds. What the
run actually proves is in tools/provenance.py, which reads where pip downloaded each distribution
from.

Uses urllib rather than curl so it runs on a bare `python:*-slim` image with nothing installed.
"""
from __future__ import annotations

import urllib.error
import urllib.request

from released import distributions

for name in distributions():
    url = f"https://pypi.org/simple/{name}/"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            status = f"HTTP {r.status} (published)"
    except urllib.error.HTTPError as e:
        status = f"HTTP {e.code} {e.reason}" + (" (name still free)" if e.code == 404 else "")
    except Exception as e:                                   # noqa: BLE001 - report, do not fail
        status = f"{type(e).__name__}: {e}"
    print(f"    {name:<18} pypi.org/simple -> {status}")

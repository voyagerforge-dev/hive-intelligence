#!/usr/bin/env bash
# Detached pipeline run — does NOT babysit. Logs to the repo's .pipeline/.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(cd ../.. && pwd)"
mkdir -p "$REPO_ROOT/.pipeline"
LOG="$REPO_ROOT/.pipeline/run-$(date -u +%Y%m%dT%H%M).log"
setsid uv run python -m okfgen.run >"$LOG" 2>&1 &
echo "pipeline detached; tail $LOG"

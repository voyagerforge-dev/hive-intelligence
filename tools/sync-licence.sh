#!/usr/bin/env bash
# Copy the root LICENSE and NOTICE into each package so wheels and sdists carry them.
#
# Copies rather than symlinks: build backends refuse a symlink pointing outside the package
# directory, and the failure mode without this is a published wheel with no licence at all.
# Run after changing either file, and before building for publication.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
for pkg in "$root"/tooling/*/; do
  cp "$root/LICENSE" "$pkg/LICENSE"
  cp "$root/NOTICE"  "$pkg/NOTICE"
  echo "synced: $(basename "$pkg")"
done

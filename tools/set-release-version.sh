#!/usr/bin/env bash
# Set the engine version on every RELEASED package, in one place.
#
# The released packages ship as ONE engine: one version means exactly the set named in
# tools/released-packages.sh and no others, which is how the corpus repository consumes them
# (one pin, one engine). So they carry one version, written here, and
# `tools/build-release.sh` refuses to build if any of them disagrees.
#
# This exists because the versions had already drifted: every pyproject said 0.1.0 while the
# repository shipped tag v0.4.0, so the version a consumer pinned was the git tag and the
# package version was fiction. Editing six places by hand is how that happened.
#
# The set is not restated here. It is read from tools/released-packages.sh, so a distribution
# added there is stamped by this script on the same edit - which is what happened to
# hive-author for 0.7.0, and what stops the next addition from being stamped by hand.
set -euo pipefail

usage() { echo "usage: $0 <version>   e.g. $0 <MAJOR.MINOR.PATCH>" >&2; exit 2; }
[ $# -eq 1 ] || usage
version="$1"

# PEP 440 release segment, optionally pre/post/dev. Refuse anything a tag could not mirror.
if ! printf '%s' "$version" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+((a|b|rc)[0-9]+)?(\.post[0-9]+)?(\.dev[0-9]+)?$'; then
  echo "error: '$version' is not a version this release path will emit" >&2; exit 1
fi

command -v uv >/dev/null || { echo "error: uv is not installed (https://docs.astral.sh/uv/)" >&2; exit 1; }

root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
. "$root/tools/released-packages.sh"

for pkg in "${RELEASED_PACKAGES[@]}"; do
  f="$root/tooling/$pkg/pyproject.toml"
  # Anchored to the [project] table's own `version = "..."` line. Every released pyproject
  # has exactly one; the check below fails loudly rather than silently editing nothing.
  before="$(grep -c '^version = "' "$f" || true)"
  [ "$before" = "1" ] || { echo "error: $f has $before top-level version lines, expected 1" >&2; exit 1; }
  sed -i -E "s|^version = \".*\"$|version = \"$version\"|" "$f"
  echo "  $pkg -> $version"
done

# The packages that name vf-hive-gen as a dependency pin it EXACTLY. Unconstrained, a consumer
# pinning vf-hive-serve==0.5.0 resolves ANY vf-hive-gen, which is a mixed engine wearing one
# version number. hive-author names it only in its `dev` extra, and that is still published
# metadata now that the distribution is released, so it moves with the rest.
for pkg in hive-serve hive-author; do
  f="$root/tooling/$pkg/pyproject.toml"
  grep -q '"vf-hive-gen==' "$f" || { echo "error: $f does not pin vf-hive-gen" >&2; exit 1; }
  sed -i -E "s|\"vf-hive-gen==[^\"]*\"|\"vf-hive-gen==$version\"|" "$f"
  echo "  $pkg requires vf-hive-gen==$version"
done

# The lockfiles record it too - each package's own member entry, and the `vf-hive-gen` entry in
# the two that depend on it - so a bump that stopped at pyproject.toml would commit a tree that
# disagrees with itself, which is the drift this script exists to end. Every package under
# tooling/ is re-locked, which is now the whole released set.
# Offline first, because a version bump changes no dependency and nothing else here needs an
# index; the network is reached only if the cache cannot answer.
echo
for lock in "$root"/tooling/*/uv.lock; do
  pkg="$(basename "$(dirname "$lock")")"
  uv lock --offline --project "$root/tooling/$pkg" >/dev/null 2>&1 \
    || uv lock --project "$root/tooling/$pkg" >/dev/null
  echo "  relocked $pkg"
done

echo
echo "Set to $version. Next: tools/build-release.sh"

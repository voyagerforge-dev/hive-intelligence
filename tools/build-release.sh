#!/usr/bin/env bash
# Build the five released distributions, and refuse to produce a release that is not coherent.
#
# This script BUILDS AND VERIFIES. It does not publish. Where the artefacts go is a separate,
# deliberate step, and keeping it separate is what lets this run on any machine, in CI, on a
# pull request, with no credential of any kind.
#
#   tools/build-release.sh            build into dist/, which is this script's own output
#                                     directory and is CLEARED on every build
#   tools/build-release.sh <outdir>   build somewhere else; that directory is never deleted,
#                                     so it must be empty or not exist yet
#
# What it refuses on, and why each one has already gone wrong or would go silently wrong:
#   - an output directory you named that already holds something (see above: yours is not
#     ours to empty, and a mistyped path is not recoverable)
#   - the five packages disagreeing on the version     (they did: 0.1.0 vs shipped tag v0.4.0)
#   - a uv.lock still recording the previous version   (the bump stopped at pyproject.toml)
#   - vf-hive-serve not pinning vf-hive-gen exactly    (it did not: a mixed engine, one number)
#   - HEAD sitting on a tag that contradicts the built version
#   - a built artefact whose recorded metadata is not the version we asked for
#   - anything in the output directory that is not one of those wheels: the publish job
#     uploads everything there, so a stray artefact would be published having been proved
#     by nothing
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
outdir="${1:-$root/dist}"
outdir_is_named="${1:+named}"
# shellcheck source=/dev/null
. "$root/tools/released-packages.sh"

command -v uv >/dev/null || { echo "error: uv is not installed (https://docs.astral.sh/uv/)" >&2; exit 1; }

echo "==> licences"
# Each pyproject declares license-files = ["LICENSE", "NOTICE"] and the per-package copies are
# gitignored, so the build FAILS without this rather than shipping an unlicensed wheel.
"$root/tools/sync-licence.sh" | sed 's/^/  /'

echo "==> version"
version=""
for pkg in "${RELEASED_PACKAGES[@]}"; do
  f="$root/tooling/$pkg/pyproject.toml"
  v="$(grep -m1 '^version = "' "$f" | sed -E 's|^version = "(.*)"$|\1|' || true)"
  [ -n "$v" ] || { echo "error: no version in $f" >&2; exit 1; }
  if [ -z "$version" ]; then version="$v"
  elif [ "$v" != "$version" ]; then
    echo "error: $pkg is $v but the engine is $version." >&2
    echo "       The five packages release as one engine. Use tools/set-release-version.sh." >&2
    exit 1
  fi
  echo "  $pkg $v"
done

pin="$(grep -oE '"vf-hive-gen==[^"]*"' "$root/tooling/hive-serve/pyproject.toml" | tr -d '"' || true)"
[ "$pin" = "vf-hive-gen==$version" ] || {
  echo "error: hive-serve requires '$pin', expected 'vf-hive-gen==$version'." >&2
  echo "       An unpinned engine dependency resolves any hive-gen behind one version number." >&2
  exit 1; }
echo "  hive-serve requires $pin"

echo "==> lockfiles"
# No wheel reads uv.lock, so a stale one breaks nothing a consumer sees - which is exactly how
# it sits unnoticed in a release commit, saying 0.5.0 beside a pyproject saying 0.6.0.
# tools/set-release-version.sh writes both; this refuses when something else wrote one of them.
python3 - "$root" "$version" "${RELEASED_PACKAGES[@]}" <<'LOCKS'
import pathlib, sys, tomllib

root, version, packages = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
released = {"vf-" + p for p in packages}
locks = sorted(root.glob("tooling/*/uv.lock"))
stale = [f"{lock.relative_to(root)} records {entry['name']} {entry.get('version')}"
         for lock in locks
         for entry in tomllib.loads(lock.read_text()).get("package", [])
         if entry.get("name") in released and entry.get("version") != version]
if stale:
    print(f"error: a lockfile disagrees with the packages, which say {version}:", file=sys.stderr)
    for s in stale:
        print("  -", s, file=sys.stderr)
    print("       tools/set-release-version.sh writes the lockfiles as well as the",
          "pyprojects; run it rather than editing a version by hand.", file=sys.stderr)
    raise SystemExit(1)
print(f"  {len(locks)} lockfiles agree on {version}")
LOCKS

# A release build is a clean tree sitting exactly on a tag; then the tag is the release marker
# and must agree with the packages. Anything else is a verification build, and saying which one
# this is beats inventing a version or refusing work that was never claiming to be a release.
if [ -n "$(git -C "$root" status --porcelain 2>/dev/null || true)" ]; then
  echo "  working tree is dirty: building $version as a verification build, not a release"
elif tag="$(git -C "$root" describe --tags --exact-match 2>/dev/null)"; then
  [ "$tag" = "v$version" ] || {
    echo "error: HEAD is tagged $tag but the packages say $version." >&2
    echo "       Tag and package version are the same fact; fix one before releasing." >&2
    exit 1; }
  echo "  HEAD is tagged $tag: this is a release build of $version"
else
  echo "  HEAD is not tagged: building $version as a verification build, not a release"
fi

echo "==> build -> $outdir"
# WHEELS ONLY. A wheel carries the package directory and the licence and nothing else; the
# sdist additionally carries tests, `.env.example`, `uv.lock` and (for hive-serve) the deploy
# example. None of that is any use to a consumer installing a pure-Python tool, and every file
# in a published artefact is a file someone has to have audited. Not building the sdist at all
# beats building one and remembering not to upload it.
if [ -z "$outdir_is_named" ]; then
  # dist/ is ours; starting from empty is what makes the artefact check below mean something.
  rm -rf "$outdir"; mkdir -p "$outdir"
else
  # A directory the operator named is never deleted. This script cannot tell a stale release
  # directory from a mistyped path, and only one of those is recoverable.
  if [ -e "$outdir" ] && [ ! -d "$outdir" ]; then
    echo "error: $outdir exists and is not a directory." >&2
    exit 1
  fi
  mkdir -p "$outdir"
  if [ -n "$(find "$outdir" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
    echo "error: $outdir is not empty, and this script will not delete a directory you named." >&2
    echo "       Empty or remove it yourself, or run with no argument to build into dist/." >&2
    exit 1
  fi
fi
for pkg in "${RELEASED_PACKAGES[@]}"; do
  uv build --wheel --project "$root/tooling/$pkg" --out-dir "$outdir" >/dev/null
  echo "  built $pkg"
done

echo "==> verify artefacts"
python3 - "$outdir" "$version" "${RELEASED_PACKAGES[@]}" <<'PY'
import pathlib, sys, zipfile, email

outdir, version, packages = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
# tooling dir name -> distribution name by convention: hive-gen ships as vf-hive-gen. The
# metadata check below is what holds that convention true; tools/released.py derives the
# same mapping for the proof scripts.
dist_of = {p: "vf-" + p for p in packages}
failures = []

for pkg in packages:
    dist = dist_of[pkg]
    stem = dist.replace("-", "_")
    wheel = outdir / f"{stem}-{version}-py3-none-any.whl"
    if not wheel.is_file():
        failures.append(f"missing artefact {wheel.name}"); continue
    with zipfile.ZipFile(wheel) as z:
        meta = email.message_from_string(z.read(f"{stem}-{version}.dist-info/METADATA").decode())
        names = z.namelist()
    if meta["Name"] != dist:
        failures.append(f"{wheel.name}: metadata Name is {meta['Name']!r}, expected {dist!r}")
    if meta["Version"] != version:
        failures.append(f"{wheel.name}: metadata Version is {meta['Version']!r}, expected {version!r}")
    # An unlicensed wheel is the exact failure tools/sync-licence.sh exists to prevent.
    for lic in ("LICENSE", "NOTICE"):
        if f"{stem}-{version}.dist-info/licenses/{lic}" not in names:
            failures.append(f"{wheel.name}: no {lic}")
    if dist == "vf-hive-serve":
        reqs = meta.get_all("Requires-Dist") or []
        if f"vf-hive-gen=={version}" not in reqs:
            failures.append(f"{wheel.name}: Requires-Dist lacks vf-hive-gen=={version}: {reqs}")
    print(f"  {wheel.name}  {wheel.stat().st_size // 1024} KB")

# Exactly the released set, and nothing beside it. A publish step uploads the whole directory,
# so a wheel nobody asked for is a distribution that reaches PyPI - irreversibly - without the
# install proof ever having requested, installed or run it.
expected = {f"{dist_of[p].replace('-', '_')}-{version}-py3-none-any.whl" for p in packages}
stray = sorted(f.name for f in outdir.iterdir()
               if f.is_file() and f.name != ".gitignore" and f.name not in expected)
if stray:
    failures.append(f"{outdir} holds files that are not one of the {len(packages)} released "
                    f"wheels, and a publish step uploads everything in it: {stray}")

if failures:
    print("\nartefact verification FAILED:", file=sys.stderr)
    for f in failures:
        print("  -", f, file=sys.stderr)
    raise SystemExit(1)
print(f"\n{len(packages)} distributions at {version}, verified. Nothing has been published.")
PY

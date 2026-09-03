#!/usr/bin/env bash
# Install the built distributions in a container that holds NO credential of ours, and run
# them for real.
#
# The defect this repository is fixing is that the consumer resolved its engine pin over SSH
# to a LAN-only forge with the author's personal key, so it built on exactly one machine and
# everyone believed otherwise. The only honest answer to that is a proof from somewhere the
# key cannot reach, so this is deliberately not a venv on the developer's machine:
#
#   - a fresh `python:3.12-slim` container, so no host site-packages and no host PATH
#   - no SSH agent, no ~/.ssh, no git credentials, no GH_TOKEN, no PyPI token: podman does
#     not pass the host environment through, and the run below prints its whole environment
#     and its failure to read this private repository so you can see that for yourself
#   - read-only mounts and nothing else: the artefacts, the proof scripts, and an OKF card
#     corpus, which is data a consumer supplies
#   - a real Postgres container for the ledger, because hive-serve has no file fallback
#
# Third-party dependencies come from public PyPI, which needs no credential. Where the five
# vf-* distributions themselves came from is not taken on trust: pip's own `--report` records
# the URL each one resolved from, and tools/provenance.py asserts it - `file://` for the
# mounted artefacts, `https://` for --from-pypi - which reads the same before and after the
# names exist on an index.
#
# Two modes, and both are worth running:
#
#   tools/verify-clean-install.sh              install the wheels just built, from a mount
#   tools/verify-clean-install.sh --from-pypi  install them from PyPI, as a consumer does
#
# The second only works after a version is published, and it is the claim that actually matters
# to a consumer: nothing local, nothing mounted, just `pip install vf-hive-serve==X`. Either way
# the run reads pip's own install report and prints the URL each of the five came from, so the
# proof does not rest on what the script meant to do.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
. "$root/tools/released-packages.sh"
source_mode=artefacts
case "${1:-}" in
  --from-pypi) source_mode=pypi ;;
  "") ;;
  *) echo "usage: $0 [--from-pypi]" >&2; exit 2 ;;
esac
corpus="${CORPUS:-$root/tooling/hive-serve/tests/fixtures/corpus}"
net=hive-clean-proof
db=hive-clean-proof-db

runtime=""
for c in podman docker; do command -v "$c" >/dev/null && { runtime="$c"; break; }; done
[ -n "$runtime" ] || { echo "error: podman or docker is required" >&2; exit 1; }
[ -d "$corpus/concepts" ] || { echo "error: no OKF corpus at $corpus (set CORPUS=)" >&2; exit 1; }

version="$(grep -m1 '^version = "' "$root/tooling/hive-gen/pyproject.toml" | sed -E 's|^version = "(.*)"$|\1|')"
if [ "$source_mode" = pypi ]; then
  echo "==> installing $version from PyPI; nothing local is built or mounted"
else
  echo "==> build the artefacts to install"
  "$root/tools/build-release.sh" >/dev/null
  echo "  dist/ holds $version"
fi

cleanup() {
  $runtime rm -f "$db" >/dev/null 2>&1 || true
  $runtime network rm "$net" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

echo "==> a real Postgres for the ledger (hive-serve has no file fallback, on purpose)"
$runtime network create "$net" >/dev/null
$runtime run -d --rm --name "$db" --network "$net" \
  -e POSTGRES_PASSWORD=proof -e POSTGRES_USER=hive -e POSTGRES_DB=hive_ledger \
  docker.io/library/postgres:16-alpine >/dev/null
for _ in $(seq 1 60); do
  $runtime exec "$db" pg_isready -U hive -d hive_ledger >/dev/null 2>&1 && break
  sleep 1
done
$runtime exec "$db" pg_isready -U hive -d hive_ledger

echo "==> the clean container"
# In --from-pypi mode dist/ is NOT mounted, so there is no local copy of the five to fall back
# on: the install can only have come off the index.
mounts=(-v "$root/tools/smoke-installed.py:/proof/smoke-installed.py:ro"
        -v "$root/tools/provenance.py:/proof/provenance.py:ro"
        -v "$root/tools/index_probe.py:/proof/index_probe.py:ro"
        -v "$root/tools/released.py:/proof/released.py:ro"
        -v "$root/tools/clean-install-inside.sh:/proof/inside.sh:ro"
        -v "$corpus:/corpus:ro")
[ "$source_mode" = pypi ] || mounts+=(-v "$root/dist:/artefacts:ro")

$runtime run --rm --network "$net" \
  --security-opt label=disable \
  "${mounts[@]}" \
  -e ENGINE_VERSION="$version" \
  -e INSTALL_SOURCE="$source_mode" \
  -e RELEASED_PACKAGES="${RELEASED_PACKAGES[*]}" \
  -e LEDGER_DSN="postgresql://hive:proof@$db:5432/hive_ledger" \
  docker.io/library/python:3.12-slim bash /proof/inside.sh

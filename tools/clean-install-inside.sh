#!/usr/bin/env bash
# Runs INSIDE the clean container started by tools/verify-clean-install.sh. Every step
# prints what it ran, so the transcript is the evidence rather than a claim about it.
set -euo pipefail

say() { printf '\n\033[1m--- %s\033[0m\n' "$*"; }

# Until 2026-09-05 this step also fetched the engine repository and failed on any success, to
# show the container could not read it. That died the day the repository was made public: it
# answers HTTP 200 to anybody now, and an anonymous read of a public repository is not a
# credential, so the probe proved nothing while failing the run - and it failed it every time,
# because its `raise SystemExit(1)` derives from BaseException and its own `except Exception`
# never caught it. Nothing here is asserted on in either direction; this step narrates what the
# container has and what it does not. Where the distributions really came from is settled in
# step 3, from pip's own resolution report, which is the fact that matters and reads the same
# either way.
say "1. what this environment has, and what it does not"
echo "\$ id && python -V"
id; python -V
echo
echo "\$ env    # the whole environment, unedited"
env | sort
echo
echo "\$ ls -a ~/.ssh /root/.ssh /etc/ssh/ssh_config.d 2>&1 | head"
# ls, not find: this is a transcript, and the reader is meant to see the command that
# was run and the "No such file or directory" it answered with.
# shellcheck disable=SC2012
ls -a ~/.ssh 2>&1 | head -3 || true
echo
echo "\$ ls ~/.netrc ~/.git-credentials ~/.config/gh 2>&1"
ls ~/.netrc ~/.git-credentials ~/.config/gh 2>&1 || true
echo
echo "\$ command -v ssh git gh    # nothing here can even speak the protocol the old pin used"
command -v ssh git gh || echo "(none installed)"

say "2. where each distribution can be resolved from, right now"
# Informational, and deliberately not an assertion either way - tools/index_probe.py says why.
# Provenance is established in step 3 instead, from what pip actually downloaded, which is the
# fact that matters whether or not a name has published yet.
python /proof/index_probe.py

# The released set is handed in rather than restated here: tools/verify-clean-install.sh
# sources tools/released-packages.sh, which is the one place it is stated, so this container
# cannot end up installing one set while another was built.
[ -n "${RELEASED_PACKAGES:-}" ] || {
  echo "error: RELEASED_PACKAGES is not set; the harness must pass the released set in" >&2
  exit 1; }
read -ra released <<<"$RELEASED_PACKAGES"

if [ "${INSTALL_SOURCE:-artefacts}" = "pypi" ]; then
  PKGS=""
  for pkg in "${released[@]}"; do PKGS="${PKGS:+$PKGS }vf-$pkg==${ENGINE_VERSION}"; done
  say "3. install them FROM PYPI, the way a consumer would"
  echo "  nothing is mounted at /artefacts: this container holds no local copy of them"
  echo "\$ pip install $PKGS"
  # shellcheck disable=SC2086
  pip install --quiet --report /tmp/report.json $PKGS
  expect_scheme="https"
else
  # The mounted wheel FILES, not `vf-name==version` requirements: a name and a version are
  # also what the index answers, and once that version is published pip prefers the index
  # copy even with the mount on `--find-links`, which would prove the published wheel rather
  # than the built one. A file path has one candidate. The filenames are the ones
  # tools/build-release.sh verifies it wrote, so a mount holding some other version fails
  # here rather than being installed. Third-party dependencies still come from PyPI.
  PKGS=""
  for pkg in "${released[@]}"; do
    PKGS="${PKGS:+$PKGS }/artefacts/vf_${pkg//-/_}-${ENGINE_VERSION}-py3-none-any.whl"
  done
  say "3. install them, from the mounted artefacts"
  echo "\$ ls /artefacts"
  ls /artefacts
  echo
  echo "\$ pip install $PKGS"
  # shellcheck disable=SC2086
  pip install --quiet --report /tmp/report.json $PKGS
  expect_scheme="file"
fi
pip list 2>/dev/null | grep -E '^vf-hive'

# Provenance, read from pip's own resolution report rather than from what we intended. This is
# what makes the run mean something: it names the URL each of them actually came from, and
# it reads the same before and after the distributions exist on an index.
echo
echo "  where pip actually got them:"
EXPECT_SCHEME="$expect_scheme" python /proof/provenance.py /tmp/report.json

say "4. run them"
cd /tmp && python /proof/smoke-installed.py --expect-version "${ENGINE_VERSION}" \
  --corpus /corpus --verdict-out /tmp/verdict.txt

say "5. hive-serve over HTTP, against the real Postgres ledger"
export CONCEPTS_DIR=/corpus/concepts CLIENTS_DIR=/corpus/clients HOST=127.0.0.1 PORT=8000
echo "\$ CONCEPTS_DIR=$CONCEPTS_DIR LEDGER_DSN=postgresql://hive:***@${LEDGER_DSN#*@} hiveserve serve --http &"
hiveserve serve --http >/tmp/serve.log 2>&1 &
serve_pid=$!
ready=""
for _ in $(seq 1 60); do
  if python - <<'PY' 2>/dev/null
import urllib.request
urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=2)
PY
  then
    ready=yes
    break
  fi
  # A server that has already exited never becomes ready; waiting out the rest of the loop
  # against a dead pid only delays the answer.
  kill -0 "$serve_pid" 2>/dev/null || break
  sleep 1
done
if [ -z "$ready" ]; then
  kill "$serve_pid" 2>/dev/null || true
  echo "error: hive-serve never answered /healthz. Its own output is the only thing that says" >&2
  echo "       why - an unreachable ledger, a rejected LEDGER_DSN, a settings refusal:" >&2
  sed 's/^/  /' /tmp/serve.log >&2
  exit 1
fi
python - <<'PY'
import json, urllib.request

def get(path):
    with urllib.request.urlopen("http://127.0.0.1:8000" + path, timeout=10) as r:
        return r.status, json.loads(r.read())

def post(path, payload):
    req = urllib.request.Request("http://127.0.0.1:8000" + path,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, json.loads(r.read())

status, body = get("/healthz")
print(f"  GET /healthz -> {status} {body}")
assert status == 200 and body == {"ok": True}

status, body = get("/concepts")
print(f"  GET /concepts -> {status}, {len(body)} cards")
for c in body[:5]:
    print(f"    {c['id']}  {c.get('title','')}")
assert status == 200 and body

status, body = get("/find_concepts?q=calibration")
print(f"  GET /find_concepts?q=calibration -> {status}, {len(body)} hits: "
      f"{[c['id'] for c in body]}")
assert status == 200 and body

card_id = body[0]["id"]
status, body = get("/card/" + card_id)
print(f"  GET /card/{card_id} -> {status}, {len(body['markdown'])} chars of markdown")
assert status == 200 and body["markdown"].startswith("---")

status, body = post("/resolve", {"ids": [card_id], "depth": 1})
print(f"  POST /resolve -> {status}, bundle of {len(body['card_ids'])}: {body['card_ids']}")
assert status == 200 and len(body["card_ids"]) > 1, "cross-link traversal returned nothing"

# The ledger, which NOTHING above this line touches: /healthz, /concepts, /find_concepts,
# /card and /resolve all read the corpus off disk, and hiveserve's connection factory is
# lazy, so every assertion so far holds just as well with no Postgres started at all. The
# heading of this step and the line below it would then be claiming a database the run never
# reached - the same "it looks finished" failure the rest of this proof is built to refuse.
# hive_ledger_rows is sampled by a real `SELECT COUNT(*)` per table against the schema
# hive-serve creates on connect, and ContentCollector SWALLOWS a failing sample and serves
# empty gauges rather than a 500, so the tables being named in the scrape is the evidence
# that the connection and the queries actually happened.
with urllib.request.urlopen("http://127.0.0.1:8000/metrics", timeout=10) as r:
    scrape = r.read().decode()
gauges = sorted(ln for ln in scrape.splitlines() if ln.startswith("hive_ledger_rows{"))
print(f"  GET /metrics -> {len(gauges)} ledger gauge(s), counted in Postgres:")
for line in gauges:
    print("    " + line)
assert {'hive_ledger_rows{table="memory"}', 'hive_ledger_rows{table="objective"}'} <= {
    ln.split(" ", 1)[0] for ln in gauges
}, "no hive_ledger_rows in the scrape: the ledger was never queried, so nothing here is " \
   "evidence of a Postgres behind this server"

print("\n  hive-serve answered from the corpus, over HTTP, with a Postgres ledger behind it.")
PY
kill "$serve_pid" 2>/dev/null || true

# Not a second claim written by hand: the smoke script's own verdict, derived from the steps
# that actually ran, so this line degrades with it instead of drifting away from it.
say "$(cat /tmp/verdict.txt), in a container with no credential of ours"

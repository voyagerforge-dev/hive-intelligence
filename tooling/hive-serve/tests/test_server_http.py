from hiveserve.config import Settings


def test_choose_transport():
    from hiveserve.server import _choose_transport
    s_http = Settings(transport="http")
    s_stdio = Settings(transport="stdio")
    assert _choose_transport(True, False, s_http) == "http"
    assert _choose_transport(False, True, s_http) == "stdio"
    assert _choose_transport(False, False, s_http) == "http"   # no flag → settings.transport
    assert _choose_transport(False, False, s_stdio) == "stdio"


def test_http_app_serves_rest_and_mounts_mcp(card_client):
    assert card_client.get("/healthz").json() == {"ok": True}
    assert card_client.get("/concepts").json()[0]["id"] == "wave-replen"
    # MCP streamable-HTTP endpoint is mounted at /mcp (transport may answer
    # 400/406 without a session, but it must NOT be 404 / shadowed by REST)
    assert card_client.get("/mcp").status_code != 404


def test_metrics_endpoint_not_shadowed_by_mcp_mount(card_client):
    r = card_client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in r.text


# --------------------------------------------------------------------------
# What a first visitor sees when a required setting is missing.
#
# `docs/guides/getting-started.md` shows the LEDGER_DSN refusal as a single line
# naming the setting and says CONCEPTS_DIR refuses the same way, and prefaces the
# whole guide with "every output below was run against this repository". The
# LEDGER_DSN one did not: `_conn_factory` raised an ordinary exception, so the
# operator got fifteen frames of click/uvicorn/psycopg internals with the
# sentence that explains the problem on the last one. The frames say nothing a
# reader can act on - the message already does - and burying it is how a
# one-setting mistake reads as a crash.
#
# These run the installed console script rather than calling `main()`, because
# the traceback is printed by the interpreter after `main()` returns control,
# which is precisely the part an in-process test cannot see.
# --------------------------------------------------------------------------

def _hiveserve(cwd, env_overrides, missing):
    import os
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    # The interpreter's own bin directory, and only there: the refusal under test must
    # come from the same environment the rest of the suite imports.
    bindir = str(Path(sys.executable).parent)
    exe = shutil.which("hiveserve", path=bindir)
    assert exe, "hiveserve console script is not installed in this environment"
    env = {k: v for k, v in os.environ.items() if k not in missing}
    # A regressed refusal reaches `uvicorn.run`, so it must not be able to take a port
    # anything else is using: port 1 is unbindable unprivileged, and the timeout below
    # is what fails the test red where it is bindable.
    env.update({"HOST": "127.0.0.1", "PORT": "1"})
    env.update(env_overrides)
    # From `cwd`, not the package root: `env_file=".env"` is resolved against the working
    # directory, and a developer's own `.env` would supply what the test removed.
    # check=False: a non-zero exit is what these tests assert on.
    return subprocess.run([exe, "serve", "--http"], capture_output=True, text=True,
                          env=env, cwd=str(cwd), check=False, timeout=60)


def test_an_unset_ledger_dsn_refuses_in_one_line_and_not_a_traceback(tmp_path):
    r = _hiveserve(tmp_path, {"CONCEPTS_DIR": str(tmp_path), "CLIENTS_DIR": ""},
                   {"LEDGER_DSN"})

    assert r.returncode == 1, r.stdout + r.stderr
    assert "Traceback" not in r.stderr, r.stderr
    assert "LEDGER_DSN" in r.stderr, r.stderr


def test_an_unset_concepts_dir_refuses_naming_the_setting_and_not_a_traceback(tmp_path):
    r = _hiveserve(tmp_path,
                   {"LEDGER_DSN": "postgresql://nobody@127.0.0.1:1/none", "CLIENTS_DIR": ""},
                   {"CONCEPTS_DIR"})

    assert r.returncode == 1, r.stdout + r.stderr
    assert "Traceback" not in r.stderr, r.stderr
    assert "CONCEPTS_DIR" in r.stderr, r.stderr

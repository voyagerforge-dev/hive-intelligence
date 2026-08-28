import pytest
from fastapi.testclient import TestClient

from hiveauthor.config import Settings
from hiveauthor.server import build_http_app

CONFIGURED = {"forge_api": "http://forge/api/v1", "forge_repo": "example/corpus",
              "forge_token": "tok", "forge_kind": "forgejo"}


def test_healthz_and_mcp_mounted():
    app = build_http_app(Settings(**CONFIGURED))
    with TestClient(app) as c:
        assert c.get("/healthz").json() == {"ok": True}
        assert c.get("/mcp").status_code != 404


@pytest.mark.parametrize("missing", ["forge_api", "forge_repo", "forge_token"])
def test_refuses_to_start_when_unconfigured(missing):
    """An unset forge_repo built `/repos//issues` and 404'd every submission while the
    contribute path was documented as working. Fail at startup instead of at runtime."""
    cfg = dict(CONFIGURED)
    cfg[missing] = ""
    with pytest.raises(RuntimeError, match=missing):
        build_http_app(Settings(**cfg))


# ---------------------------------------------------------------------------
# Choosing a forge, and a token that rotates. Both arrived 2026-08-15 when EXAMPLECO
# returned to github.com and started authenticating as a GitHub App.
# ---------------------------------------------------------------------------

def test_forge_kind_selects_the_client():
    from hiveauthor.issue_client import ForgejoIssueClient, GitHubIssueClient
    from hiveauthor.server import _issue_client_factory

    gh = _issue_client_factory(Settings(**{**CONFIGURED, "forge_kind": "github"}))()
    assert isinstance(gh, GitHubIssueClient)
    fj = _issue_client_factory(Settings(**{**CONFIGURED, "forge_kind": "forgejo"}))()
    assert isinstance(fj, ForgejoIssueClient)


def test_an_unknown_forge_kind_is_refused_at_startup():
    """Not defaulted. Guessing wrong sends label IDs to GitHub, or names to Forgejo,
    and the submission fails at the moment a consultant is waiting on it."""
    with pytest.raises(RuntimeError, match="forge_kind"):
        build_http_app(Settings(**{**CONFIGURED, "forge_kind": "gitlab"}))


def test_a_token_file_is_read_per_call_not_at_startup(tmp_path):
    """A GitHub App token lasts an hour; this process runs for days."""
    from hiveauthor.server import _issue_client_factory

    f = tmp_path / "token"
    f.write_text("first\n")
    cfg = {**CONFIGURED, "forge_token": "", "forge_token_file": str(f),
           "forge_kind": "github"}
    client = _issue_client_factory(Settings(**cfg))()

    assert client._token() == "first"       # whitespace stripped
    f.write_text("second\n")
    assert client._token() == "second"      # picked up without a restart


def test_either_a_token_or_a_token_file_satisfies_configuration(tmp_path):
    f = tmp_path / "token"
    f.write_text("tok")
    cfg = {**CONFIGURED, "forge_token": "", "forge_token_file": str(f),
           "forge_kind": "forgejo"}
    build_http_app(Settings(**cfg))          # must not raise


def test_neither_a_token_nor_a_file_still_refuses():
    cfg = {**CONFIGURED, "forge_token": "", "forge_kind": "forgejo"}
    with pytest.raises(RuntimeError, match="forge_token"):
        build_http_app(Settings(**cfg))


def test_a_missing_token_file_fails_at_startup_not_at_submission_time(tmp_path):
    """Reading it once at startup is the only check that can happen before a
    consultant is waiting. A file that appears later is fine; one that never
    existed is a misconfiguration."""
    cfg = {**CONFIGURED, "forge_token": "",
           "forge_token_file": str(tmp_path / "absent"), "forge_kind": "github"}
    with pytest.raises(RuntimeError, match="forge_token_file"):
        build_http_app(Settings(**cfg))

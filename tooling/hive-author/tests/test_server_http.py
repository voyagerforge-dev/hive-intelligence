import pytest
from fastapi.testclient import TestClient

from hiveauthor.config import Settings
from hiveauthor.server import build_http_app

CONFIGURED = dict(forge_api="http://forge/api/v1", forge_repo="example/corpus", forge_token="tok")


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

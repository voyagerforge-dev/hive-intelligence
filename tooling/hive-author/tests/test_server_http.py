from fastapi.testclient import TestClient

from hiveauthor.config import Settings
from hiveauthor.server import build_http_app


def test_healthz_and_mcp_mounted():
    app = build_http_app(Settings())
    with TestClient(app) as c:
        assert c.get("/healthz").json() == {"ok": True}
        assert c.get("/mcp").status_code != 404

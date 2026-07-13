from fastapi.testclient import TestClient

from okfserve.config import Settings
from okfserve.server import build_http_app

CARD = """---
title: Wave Replen
description: replen feeds waves
related: []
sources: [wms.md]
---
Body.
"""


def test_choose_transport():
    from okfserve.server import _choose_transport
    s_http = Settings(transport="http")
    s_stdio = Settings(transport="stdio")
    assert _choose_transport(True, False, s_http) == "http"
    assert _choose_transport(False, True, s_http) == "stdio"
    assert _choose_transport(False, False, s_http) == "http"   # no flag → settings.transport
    assert _choose_transport(False, False, s_stdio) == "stdio"


def test_http_app_serves_rest_and_mounts_mcp(tmp_path):
    (tmp_path / "wave-replen.md").write_text(CARD)
    s = Settings(concepts_dir=str(tmp_path), okf_data_dir=str(tmp_path))
    app = build_http_app(s)
    with TestClient(app) as c:
        assert c.get("/healthz").json() == {"ok": True}
        assert c.get("/concepts").json()[0]["id"] == "wave-replen"
        # MCP streamable-HTTP endpoint is mounted at /mcp (transport may answer
        # 400/406 without a session, but it must NOT be 404 / shadowed by REST)
        assert c.get("/mcp").status_code != 404


def test_metrics_endpoint_not_shadowed_by_mcp_mount(tmp_path):
    (tmp_path / "wave-replen.md").write_text(CARD)
    s = Settings(concepts_dir=str(tmp_path), okf_data_dir=str(tmp_path))
    app = build_http_app(s)
    with TestClient(app) as c:
        r = c.get("/metrics")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        assert "http_requests_total" in r.text

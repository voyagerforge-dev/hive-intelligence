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

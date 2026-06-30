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

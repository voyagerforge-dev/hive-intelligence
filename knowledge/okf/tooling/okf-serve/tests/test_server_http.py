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
    # the MCP streamable-HTTP app is mounted (its route lives at /mcp)
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any("mcp" in p for p in paths)
    # lifespan (mcp.session_manager.run) starts cleanly and REST works under it
    with TestClient(app) as c:
        assert c.get("/healthz").json() == {"ok": True}
        assert c.get("/concepts").json()[0]["id"] == "wave-replen"

from fastapi import FastAPI
from fastapi.testclient import TestClient

from hiveserve.app import build_rest_router
from hiveserve.config import Settings

CARD = """---
title: Wave Replen
description: replen feeds waves
related: []
sources: [wms.md]
---
Body.
"""


def _client(tmp_path):
    (tmp_path / "wave-replen.md").write_text(CARD)
    s = Settings(concepts_dir=str(tmp_path))
    app = FastAPI()
    app.include_router(build_rest_router(s))
    return TestClient(app)


def test_concepts_and_card(tmp_path):
    c = _client(tmp_path)
    assert c.get("/healthz").json() == {"ok": True}
    assert c.get("/concepts").json()[0]["id"] == "wave-replen"
    assert "Body." in c.get("/card/wave-replen").json()["markdown"]
    assert c.get("/card/nope").status_code == 404


def test_resolve(tmp_path):
    c = _client(tmp_path)
    r = c.post("/resolve", json={"ids": ["wave-replen"], "depth": 1}).json()
    assert r["card_ids"] == ["wave-replen"]


def test_card_route_accepts_path_id_with_slash(tmp_path):
    sub = tmp_path / "osci"
    sub.mkdir()
    (sub / "omni-framework.md").write_text(
        "---\ntitle: Omni\ndescription: d\nrelated: []\nsources: []\n---\n\nOmni body.\n")
    s = Settings(concepts_dir=str(tmp_path))
    app = FastAPI()
    app.include_router(build_rest_router(s))
    c = TestClient(app)
    r = c.get("/card/osci/omni-framework")
    assert r.status_code == 200
    assert "Omni body." in r.json()["markdown"]
    assert r.json()["id"] == "osci/omni-framework"

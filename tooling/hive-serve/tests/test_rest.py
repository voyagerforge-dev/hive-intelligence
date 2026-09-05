from fastapi import FastAPI
from fastapi.testclient import TestClient

from hiveserve.app import build_rest_router
from hiveserve.config import Settings

CARD = """---
title: Wave Replen
description: replen feeds waves
related: []
sources: [widgets.md]
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
    sub = tmp_path / "gadgets"
    sub.mkdir()
    (sub / "omni-framework.md").write_text(
        "---\ntitle: Omni\ndescription: d\nrelated: []\nsources: []\n---\n\nOmni body.\n")
    s = Settings(concepts_dir=str(tmp_path))
    app = FastAPI()
    app.include_router(build_rest_router(s))
    c = TestClient(app)
    r = c.get("/card/gadgets/omni-framework")
    assert r.status_code == 200
    assert "Omni body." in r.json()["markdown"]
    assert r.json()["id"] == "gadgets/omni-framework"


def test_find_concepts_route_serves_no_client_card_and_takes_no_client(tmp_path):
    """The REST door searches shared knowledge only, like `/concepts` and `/resolve`.

    `find_concepts` gained a `client` argument so the MCP door - which resolves an owner
    from a trusted proxy header - can search a client's own memory. This door carries no
    identity, so a client name here would be an assertion by an anonymous caller. The
    clients tree is not handed to the search at all, so a client card cannot be in the
    candidate set whatever the query string says.
    """
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    (concepts / "widgets").mkdir(parents=True)
    (concepts / "widgets" / "allocation-process.md").write_text(
        "---\ntitle: Allocation Process\ndescription: how allocation assigns inventory\n---\n\nbody\n")
    (clients / "alpha" / "memory").mkdir(parents=True)
    (clients / "alpha" / "memory" / "second-scan.md").write_text(
        "---\ntitle: Alpha second scan\ndescription: an extra allocation scan step\n"
        "type: memory\n---\n\nmem\n")
    s = Settings(concepts_dir=str(concepts), clients_dir=str(clients))
    app = FastAPI()
    app.include_router(build_rest_router(s))
    c = TestClient(app)

    hits = c.get("/find_concepts", params={"q": "allocation scan"}).json()
    assert [h["id"] for h in hits] == ["widgets/allocation-process"]
    # an unknown query parameter is ignored by FastAPI rather than scoping anything
    named = c.get("/find_concepts", params={"q": "allocation scan", "client": "alpha"}).json()
    assert named == hits

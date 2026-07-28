

def test_rest_resolve_rejects_client_scoping_rather_than_ignoring_it():
    """The REST door serves shared knowledge only. Client-scoped cards are reachable
    through MCP, which carries an identity.

    Silently ignoring `client` would hand the caller a 200 and a shared-only answer with
    no signal that the scoping they asked for was never applied, which is the worst of
    both: it looks like isolation is working when nothing is enforcing it."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from hiveserve.app import build_rest_router
    from hiveserve.config import Settings

    app = FastAPI()
    app.include_router(build_rest_router(Settings(concepts_dir="tests/fixtures/corpus/concepts")))
    c = TestClient(app)

    assert c.post("/resolve", json={"ids": ["widget/calibration-routine"]}).status_code == 200
    assert c.post("/resolve", json={"ids": ["x"], "client": "alpha"}).status_code == 422

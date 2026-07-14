"""Shared fixtures for okf-serve tests.

The single-card app scaffold (write a card, build the full HTTP app, open a
TestClient with lifespan) was duplicated across test_metrics.py and
test_server_http.py; it lives here now."""
import pytest
from fastapi.testclient import TestClient

from okfserve.config import Settings
from okfserve.server import build_http_app

CARD = "---\ntitle: Wave Replen\ndescription: replen feeds waves\nrelated: []\nsources: [wms.md]\n---\nBody.\n"


@pytest.fixture
def card_settings(tmp_path):
    """Settings over a tmp corpus holding one card (id `wave-replen`)."""
    (tmp_path / "wave-replen.md").write_text(CARD)
    return Settings(concepts_dir=str(tmp_path), okf_data_dir=str(tmp_path))


@pytest.fixture
def card_client(card_settings):
    """TestClient over the full HTTP app (lifespan running) for the card corpus."""
    with TestClient(build_http_app(card_settings)) as client:
        yield client

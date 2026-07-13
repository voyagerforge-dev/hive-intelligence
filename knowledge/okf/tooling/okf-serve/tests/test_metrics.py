from okfserve import metrics


def test_render_returns_prometheus_text_and_content_type():
    body, content_type = metrics.render()
    assert isinstance(body, bytes)
    assert content_type.startswith("text/plain")
    # metric object names are present in the exposition once observed
    metrics.HTTP_REQUESTS.labels(endpoint="/healthz", method="GET", status="200").inc()
    body, _ = metrics.render()
    text = body.decode()
    assert "http_requests_total" in text
    assert "mcp_tool_calls_total" in text or "mcp_tool_calls" in text


def test_metric_objects_have_expected_labels():
    # smoke: labelling with the documented label set does not raise
    metrics.HTTP_LATENCY.labels(endpoint="/resolve", method="POST").observe(0.01)
    metrics.TOOL_CALLS.labels(tool="resolve", outcome="ok").inc()
    metrics.TOOL_LATENCY.labels(tool="resolve").observe(0.01)


from fastapi.testclient import TestClient

from okfserve.config import Settings
from okfserve.server import build_http_app

CARD = ("---\ntitle: Wave Replen\ndescription: d\nrelated: []\nsources: [wms.md]\n---\nBody.\n")


def _sample(name, labels):
    return metrics.REGISTRY.get_sample_value(name, labels) or 0.0


def test_endpoint_label_normalizes_and_skips_mcp():
    assert metrics._endpoint_label("/healthz") == "/healthz"
    assert metrics._endpoint_label("/card/osci/omni-framework") == "/card/{id}"
    assert metrics._endpoint_label("/mcp") is None       # skipped: measured at tool layer
    assert metrics._endpoint_label("/mcp/anything") is None


def test_http_request_increments_counter(tmp_path):
    (tmp_path / "wave-replen.md").write_text(CARD)
    s = Settings(concepts_dir=str(tmp_path), okf_data_dir=str(tmp_path))
    app = build_http_app(s)
    before = _sample("http_requests_total",
                     {"endpoint": "/healthz", "method": "GET", "status": "200"})
    with TestClient(app) as c:
        assert c.get("/healthz").status_code == 200
    after = _sample("http_requests_total",
                    {"endpoint": "/healthz", "method": "GET", "status": "200"})
    assert after == before + 1

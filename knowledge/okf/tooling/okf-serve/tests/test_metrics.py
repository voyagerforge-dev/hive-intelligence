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

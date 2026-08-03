import pytest

from hiveserve import metrics


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


def _sample(name, labels):
    return metrics.REGISTRY.get_sample_value(name, labels) or 0.0


def test_endpoint_label_normalizes_and_skips_mcp():
    assert metrics._endpoint_label("/healthz") == "/healthz"
    assert metrics._endpoint_label("/card/gadgets/omni-framework") == "/card/{id}"
    assert metrics._endpoint_label("/mcp") is None       # skipped: measured at tool layer
    assert metrics._endpoint_label("/mcp/anything") is None
    assert metrics._endpoint_label("/metrics") is None   # skipped: self-scrape pollution


def test_http_request_increments_counter(card_client):
    before = _sample("http_requests_total",
                     {"endpoint": "/healthz", "method": "GET", "status": "200"})
    assert card_client.get("/healthz").status_code == 200
    after = _sample("http_requests_total",
                    {"endpoint": "/healthz", "method": "GET", "status": "200"})
    assert after == before + 1


def test_track_tool_counts_ok():
    @metrics.track_tool("demo_ok")
    def f(x):
        return x + 1
    before = _sample("mcp_tool_calls_total", {"tool": "demo_ok", "outcome": "ok"})
    assert f(1) == 2
    after = _sample("mcp_tool_calls_total", {"tool": "demo_ok", "outcome": "ok"})
    assert after == before + 1


def test_track_tool_counts_error_and_reraises():
    @metrics.track_tool("demo_err")
    def f():
        raise ValueError("boom")
    before = _sample("mcp_tool_calls_total", {"tool": "demo_err", "outcome": "error"})
    with pytest.raises(ValueError):
        f()
    after = _sample("mcp_tool_calls_total", {"tool": "demo_err", "outcome": "error"})
    assert after == before + 1


def test_track_tool_preserves_signature():
    import inspect

    @metrics.track_tool("demo_sig")
    def f(a: int, b: str = "x") -> str:
        return b * a
    assert list(inspect.signature(f).parameters) == ["a", "b"]


def test_content_collector_caches_within_ttl():
    calls = {"n": 0}
    clock = {"t": 0.0}

    def sample():
        calls["n"] += 1
        return {"cards": {("widgets", "operational"): 3, ("gadgets", None): 1},
                "ledger": {"objective": 2, "memory": 5}}

    coll = metrics.ContentCollector(sample, ttl_s=30.0, clock=lambda: clock["t"])
    list(coll.collect())            # first collect → samples
    clock["t"] = 10.0
    list(coll.collect())            # within TTL → cached
    assert calls["n"] == 1
    clock["t"] = 45.0
    list(coll.collect())            # past TTL → resample
    assert calls["n"] == 2


def test_content_collector_emits_gauges():
    def sample():
        return {"cards": {("widgets", "operational"): 3},
                "ledger": {"objective": 2, "memory": 5}}
    coll = metrics.ContentCollector(sample, ttl_s=30.0, clock=lambda: 0.0)
    families = {m.name: m for m in coll.collect()}
    assert "hive_corpus_cards" in families
    assert "hive_ledger_rows" in families
    card_samples = {(s.labels["product"], s.labels["regime"]): s.value
                    for s in families["hive_corpus_cards"].samples}
    assert card_samples[("widgets", "operational")] == 3
    ledger_samples = {s.labels["table"]: s.value
                      for s in families["hive_ledger_rows"].samples}
    assert ledger_samples == {"objective": 2, "memory": 5}


def test_content_collector_survives_sample_failure():
    clock = {"t": 0.0}

    def failing_sample():
        raise RuntimeError("corpus read blew up")

    # No prior cache: collector must still yield both families, with zero samples.
    coll = metrics.ContentCollector(failing_sample, ttl_s=30.0, clock=lambda: clock["t"])
    families = {m.name: m for m in coll.collect()}
    assert "hive_corpus_cards" in families
    assert "hive_ledger_rows" in families
    assert families["hive_corpus_cards"].samples == []
    assert families["hive_ledger_rows"].samples == []

    # Last-known-good: prime with one good sample, then fail past the TTL window;
    # collect() should keep serving the previously-cached values, not raise/blank out.
    calls = {"n": 0, "fail": False}

    def flaky_sample():
        calls["n"] += 1
        if calls["fail"]:
            raise RuntimeError("transient ledger read error")
        return {"cards": {("widgets", "operational"): 3}, "ledger": {"objective": 2, "memory": 5}}

    coll2 = metrics.ContentCollector(flaky_sample, ttl_s=30.0, clock=lambda: clock["t"])
    list(coll2.collect())  # primes good cache
    clock["t"] = 45.0      # past TTL
    calls["fail"] = True
    families2 = {m.name: m for m in coll2.collect()}
    card_samples = {(s.labels["product"], s.labels["regime"]): s.value
                    for s in families2["hive_corpus_cards"].samples}
    assert card_samples[("widgets", "operational")] == 3
    ledger_samples = {s.labels["table"]: s.value
                      for s in families2["hive_ledger_rows"].samples}
    assert ledger_samples == {"objective": 2, "memory": 5}


def test_content_samples_counts_fixture_corpus(tmp_path):
    from hiveserve import ledger
    concepts = tmp_path / "concepts"; clients = tmp_path / "clients"
    (concepts / "widgets").mkdir(parents=True)
    (concepts / "widgets" / "a.md").write_text(
        "---\ntitle: A\ndescription: d\nproduct: widgets\nregime: operational\n---\nbody\n")
    (concepts / "widgets" / "b.md").write_text(
        "---\ntitle: B\ndescription: d\nproduct: widgets\nregime: operational\n---\nbody\n")
    db = tmp_path / "obj.db"

    def factory():
        return ledger.session(db)
    with factory() as conn:
        ledger.start_objective(conn, owner="o", mode="investigate", goal="g")
        ledger.remember(conn, owner="o", text="t")
    out = metrics.content_samples(str(concepts), str(clients), factory)
    assert out["cards"][("widgets", "operational")] == 2
    assert out["ledger"] == {"objective": 1, "memory": 1}


# --------------------------------------------------------------------------
# Database-object tier. These cards are the majority of a real corpus and are
# invisible to hive_corpus_cards by design, so they get their own gauge and the
# alert watches both.
# --------------------------------------------------------------------------


def test_db_object_samples_counts_the_on_demand_tier(tmp_path):
    concepts = tmp_path / "concepts"
    (concepts / "widgets" / "db" / "plsql").mkdir(parents=True)
    (concepts / "widgets" / "db" / "tables").mkdir(parents=True)
    (concepts / "widgets" / "db" / "plsql" / "A_VIEW.md").write_text("---\ntype: dbobject\n---\n")
    (concepts / "widgets" / "db" / "tables" / "B_TAB.md").write_text("---\ntype: dbobject\n---\n")
    # index.md and log.md are bookkeeping, not cards, and must not be counted.
    (concepts / "widgets" / "db" / "index.md").write_text("# index\n")
    # An ordinary concept sits outside db/ and belongs to the other gauge.
    (concepts / "widgets" / "ordinary.md").write_text("---\ntitle: T\nproduct: widgets\n---\n")

    assert metrics.db_object_samples(str(concepts)) == {"widgets": 2}


def test_db_object_samples_is_empty_when_the_corpus_is_missing(tmp_path):
    """The mount going stale is the failure this exists to catch, so absence must
    read as zero rather than raise: a collector that throws takes /metrics with it."""
    assert metrics.db_object_samples(str(tmp_path / "gone")) == {}


def test_db_object_gauge_is_exported_alongside_the_card_gauge(tmp_path):
    from hiveserve import ledger

    concepts = tmp_path / "concepts"
    (concepts / "widgets" / "db").mkdir(parents=True)
    (concepts / "widgets" / "db" / "T.md").write_text("---\ntype: dbobject\n---\n")
    (concepts / "widgets" / "c.md").write_text("---\ntitle: C\nproduct: widgets\n---\n")
    db = tmp_path / "obj.db"

    def factory():
        return ledger.session(db)

    with factory() as conn:
        ledger.start_objective(conn, owner="o", mode="investigate", goal="g")

    collector = metrics.ContentCollector(
        lambda: metrics.content_samples(str(concepts), str(tmp_path / "clients"), factory))
    families = {f.name: f for f in collector.collect()}

    assert "hive_corpus_db_objects" in families
    assert {s.labels["product"]: s.value
            for s in families["hive_corpus_db_objects"].samples} == {"widgets": 1.0}
    # The db tier must NOT be double-counted into hive_corpus_cards.
    assert sum(s.value for s in families["hive_corpus_cards"].samples) == 1.0


def test_empty_corpus_yields_a_zero_sum_not_a_missing_series(tmp_path):
    """What the alert keys on. A corpus that has vanished must produce gauges that
    sum to zero, and must not make the collector raise."""
    from hiveserve import ledger

    db = tmp_path / "obj.db"

    def factory():
        return ledger.session(db)

    with factory() as conn:
        ledger.start_objective(conn, owner="o", mode="investigate", goal="g")

    collector = metrics.ContentCollector(
        lambda: metrics.content_samples(
            str(tmp_path / "gone"), str(tmp_path / "gone-too"), factory))
    families = {f.name: f for f in collector.collect()}

    assert sum(s.value for s in families["hive_corpus_cards"].samples) == 0
    assert sum(s.value for s in families["hive_corpus_db_objects"].samples) == 0

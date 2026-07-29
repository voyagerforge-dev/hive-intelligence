"""Prometheus metrics for hive-serve (LLM-free connector). One custom registry;
HTTP + MCP-tool instrumentation objects; content collector registered at app build.
No `client` label anywhere (cardinality rule)."""
from __future__ import annotations

import functools
import time
from pathlib import Path

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)
from prometheus_client.core import GaugeMetricFamily

from hiveserve.resolver import load_index

REGISTRY = CollectorRegistry()

HTTP_REQUESTS = Counter(
    "http_requests_total", "hive-serve HTTP requests",
    ["endpoint", "method", "status"], registry=REGISTRY)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds", "hive-serve HTTP request latency",
    ["endpoint", "method"], registry=REGISTRY)

TOOL_CALLS = Counter(
    "mcp_tool_calls_total", "hive-serve MCP tool calls",
    ["tool", "outcome"], registry=REGISTRY)
TOOL_LATENCY = Histogram(
    "mcp_tool_duration_seconds", "hive-serve MCP tool latency",
    ["tool"], registry=REGISTRY)


def render() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def track_tool(name: str):
    """Count + time an MCP tool call. outcome='error' on exception (then re-raise).
    Signature-preserving so FastMCP still builds the tool schema from it."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            outcome = "ok"
            try:
                return fn(*args, **kwargs)
            except Exception:
                outcome = "error"
                raise
            finally:
                TOOL_LATENCY.labels(tool=name).observe(time.perf_counter() - start)
                TOOL_CALLS.labels(tool=name, outcome=outcome).inc()
        return wrapper
    return deco


# Known REST endpoints. Anything else (the /mcp mount, unknowns) is skipped to keep
# cardinality bounded and preserve the plane split (MCP usage is a tool-layer metric).
# /metrics itself is deliberately excluded: counting Prometheus's own scrape would
# dilute the 5xx-ratio alert denominator and dominate the per-endpoint rate panel.
_STATIC = {"/healthz", "/concepts", "/resolve"}


def _endpoint_label(path: str) -> str | None:
    if path in _STATIC:
        return path
    if path == "/card" or path.startswith("/card/"):
        return "/card/{id}"
    return None  # /mcp and everything else: not measured here


class PrometheusHTTPMiddleware:
    """Pure-ASGI: times a REST request and records status. Reads only the response
    start message, so it never buffers a streaming (MCP) response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        endpoint = _endpoint_label(scope["path"])
        if endpoint is None:
            await self.app(scope, receive, send)
            return
        method = scope["method"]
        status_holder = {"code": 500}

        async def _send(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
            await send(message)

        start = time.perf_counter()
        try:
            await self.app(scope, receive, _send)
        finally:
            HTTP_LATENCY.labels(endpoint=endpoint, method=method).observe(
                time.perf_counter() - start)
            HTTP_REQUESTS.labels(
                endpoint=endpoint, method=method, status=str(status_holder["code"]),
            ).inc()


def db_object_samples(concepts_dir) -> dict[str, int]:
    """Count the on-demand database-object tier, per product.

    ``load_index`` deliberately skips ``concepts/<product>/db/**`` because those cards are
    resolved on demand rather than listed. That makes them invisible to okf_corpus_cards,
    and on a corpus with a real schema behind it they are the large majority of it:
    commonly several thousand of a few thousand more. An alert built only on okf_corpus_cards would therefore report a healthy
    corpus while almost all of it was missing.

    Counted by directory walk rather than by parsing frontmatter: this is a presence
    signal, and parsing 7,000 files on a 30s cache refresh would not earn its cost.
    """
    root = Path(concepts_dir)
    counts: dict[str, int] = {}
    if not root.is_dir():
        return counts
    for product_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        db_dir = product_dir / "db"
        if not db_dir.is_dir():
            continue
        n = sum(1 for p in db_dir.rglob("*.md") if p.name not in ("index.md", "log.md"))
        if n:
            counts[product_dir.name] = n
    return counts


def content_samples(concepts_dir, clients_dir, conn_factory) -> dict:
    cards: dict[tuple, int] = {}
    for c in load_index(concepts_dir, clients_dir):
        key = (c.get("product") or "none", c.get("regime") or "none")
        cards[key] = cards.get(key, 0) + 1
    with conn_factory() as conn:
        obj = conn.execute("SELECT COUNT(*) FROM objective").fetchone()[0]
        mem = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    return {"cards": cards, "db_objects": db_object_samples(concepts_dir),
            "ledger": {"objective": obj, "memory": mem}}


class ContentCollector:
    """TTL-cached corpus/ledger size gauges. Refreshes sample_fn() at most once per
    ttl_s so a scrape never recounts the whole corpus."""

    def __init__(self, sample_fn, ttl_s: float = 30.0, clock=time.perf_counter):
        self._sample_fn = sample_fn
        self._ttl = ttl_s
        self._clock = clock
        self._cache: dict | None = None
        self._last = 0.0

    def _samples(self) -> dict:
        now = self._clock()
        if self._cache is None or (now - self._last) >= self._ttl:
            try:
                self._cache = self._sample_fn()
            except Exception:  # noqa: BLE001 - a scrape must never take down /metrics
                # A scrape must degrade to stale/empty content gauges, never take
                # down the whole /metrics endpoint. Fall back to last-known-good,
                # or an empty-but-valid shape if we have no prior sample at all.
                if self._cache is None:
                    self._cache = {"cards": {}, "db_objects": {}, "ledger": {}}
            # Always advance _last, even on failure, so a hard-failing sample_fn
            # is retried at most once per TTL window instead of on every scrape.
            self._last = now
        return self._cache

    def collect(self):
        data = self._samples()
        cards = GaugeMetricFamily(
            "okf_corpus_cards", "OKF cards on disk by product and regime facet",
            labels=["product", "regime"])
        # Defensive sort key: content_samples normalizes facets to "none", but a
        # raw None from any sample_fn would make plain tuple-sort raise (None < str).
        for (product, regime), n in sorted(data["cards"].items(),
                                           key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
            cards.add_metric([str(product), str(regime)], n)
        yield cards
        db = GaugeMetricFamily(
            "okf_corpus_db_objects",
            "OKF database-object cards on disk by product (the on-demand tier, "
            "excluded from okf_corpus_cards)", labels=["product"])
        for product, n in sorted(data.get("db_objects", {}).items()):
            db.add_metric([str(product)], n)
        yield db
        rows = GaugeMetricFamily(
            "okf_ledger_rows", "OKF ledger row counts by table", labels=["table"])
        for table, n in sorted(data["ledger"].items()):
            rows.add_metric([table], n)
        yield rows


def register_content_collector(concepts_dir, clients_dir, conn_factory, ttl_s: float = 30.0):
    REGISTRY.register(
        ContentCollector(lambda: content_samples(concepts_dir, clients_dir, conn_factory),
                         ttl_s=ttl_s))

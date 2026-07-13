"""Prometheus metrics for okf-serve (LLM-free connector). One custom registry;
HTTP + MCP-tool instrumentation objects; content collector registered at app build.
No `client` label anywhere (cardinality rule)."""
from __future__ import annotations

import functools
import time

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest

REGISTRY = CollectorRegistry()

HTTP_REQUESTS = Counter(
    "http_requests_total", "okf-serve HTTP requests",
    ["endpoint", "method", "status"], registry=REGISTRY)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds", "okf-serve HTTP request latency",
    ["endpoint", "method"], registry=REGISTRY)

TOOL_CALLS = Counter(
    "mcp_tool_calls_total", "okf-serve MCP tool calls",
    ["tool", "outcome"], registry=REGISTRY)
TOOL_LATENCY = Histogram(
    "mcp_tool_duration_seconds", "okf-serve MCP tool latency",
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
_STATIC = {"/healthz", "/concepts", "/resolve", "/metrics"}


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
            HTTP_REQUESTS.labels(endpoint=endpoint, method=method,
                                 status=str(status_holder["code"])).inc()

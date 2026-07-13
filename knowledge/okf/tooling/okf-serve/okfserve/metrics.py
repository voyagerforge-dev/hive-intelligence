"""Prometheus metrics for okf-serve (LLM-free connector). One custom registry;
HTTP + MCP-tool instrumentation objects; content collector registered at app build.
No `client` label anywhere (cardinality rule)."""
from __future__ import annotations

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

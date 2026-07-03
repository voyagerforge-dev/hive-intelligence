# OKF serving layer — container image.
# Mirrors the project-hive connector pattern (python:3.12-slim, non-root, uvicorn on :8000).
# okf-serve depends on the local okfgen package, so both are installed from the repo checkout.
# The card corpus is NOT baked in — it is mounted at /data/concepts (a git checkout kept fresh
# by a host-side `git pull` timer), so content updates need no image rebuild.
FROM python:3.12-slim
WORKDIR /app

# Local path deps: install okfgen first (okf-serve requires it), then okf-serve.
COPY tooling/okf-gen /app/okf-gen
COPY tooling/okf-serve /app/okf-serve
RUN pip install --no-cache-dir ./okf-gen ./okf-serve \
    && useradd -u 1001 -m svc \
    && mkdir -p /data/ledger \
    && chown -R svc /app /data
USER svc

EXPOSE 8000
# Read-only knowledge connector: LLM-free, no secrets. Identity comes from the mcp-authmap
# shim / edge as `x-vf-identity` (same as the other connectors).
ENV TRANSPORT=http \
    HOST=0.0.0.0 \
    PORT=8000 \
    CONCEPTS_DIR=/data/concepts \
    OKF_DATA_DIR=/data/ledger \
    IDENTITY_HEADER=x-vf-identity \
    OKF_DEFAULT_OWNER=local-operator
# OpenAPI: /openapi.json · /docs   ·   MCP: /mcp   ·   health: /healthz
CMD ["okfserve", "serve", "--http"]

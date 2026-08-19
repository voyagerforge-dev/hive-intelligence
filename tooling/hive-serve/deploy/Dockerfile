# OKF serving layer — container image.
# Mirrors the project-hive connector pattern (python:3.12-slim, non-root, uvicorn on :8000).
# hive-serve depends on the local hivegen package, so both are installed from the repo checkout.
# The card corpus is NOT baked in — it is mounted at /data/concepts (a git checkout kept fresh
# by a host-side `git pull` timer), so content updates need no image rebuild.
FROM python:3.12-slim
WORKDIR /app

# Local path deps: install hivegen first (hive-serve requires it), then hive-serve.
COPY tooling/hive-gen /app/hive-gen
COPY tooling/hive-serve /app/hive-serve
RUN pip install --no-cache-dir ./hive-gen ./hive-serve \
    && useradd -u 1001 -m svc \
    && mkdir -p /data/scratch \
    && chown -R svc /app /data
USER svc

EXPOSE 8000
# Read-only knowledge connector: LLM-free, no secrets. Identity comes from the mcp-authmap
# shim / edge as `x-vf-identity` (same as the other connectors).
#
# LEDGER_DSN is deliberately NOT defaulted here. The ledger is Postgres since 2026-08-19 and
# a default would be a plausible-looking connection string that points nowhere; hive-serve
# refuses to start without one, which is the intended behaviour. OKF_DATA_DIR is no longer
# the ledger, only non-ledger scratch, and is renamed here so a stale mount at /data/ledger
# fails visibly rather than being silently written to.
ENV TRANSPORT=http \
    HOST=0.0.0.0 \
    PORT=8000 \
    CONCEPTS_DIR=/data/concepts \
    CLIENTS_DIR=/data/clients \
    OKF_DATA_DIR=/data/scratch \
    IDENTITY_HEADER=x-vf-identity \
    OKF_DEFAULT_OWNER=local-operator
# OpenAPI: /openapi.json · /docs   ·   MCP: /mcp   ·   health: /healthz
CMD ["hiveserve", "serve", "--http"]

"""Entrypoint: hive-author HTTP MCP server (write-only)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from hiveauthor import metrics
from hiveauthor.config import get_settings
from hiveauthor.mcp_app import build_mcp


def _issue_client_factory(settings):
    from hiveauthor.issue_client import ForgejoIssueClient
    missing = [n for n in ("forge_api", "forge_repo", "forge_token") if not getattr(settings, n)]
    if missing:
        # Refuse to start rather than serve a client that builds `/repos//issues` and
        # 404s every submission while reporting success. That exact gap ran unnoticed
        # from deployment until 2026-08-11.
        raise RuntimeError(f"hive-author is not configured: missing {', '.join(missing)}")
    return lambda: ForgejoIssueClient(settings.forge_api, settings.forge_repo, settings.forge_token)


def build_http_app(settings):
    from fastapi import FastAPI

    mcp = build_mcp(settings, _issue_client_factory(settings))

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="OKF Author", lifespan=lifespan)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    # Declared BEFORE the catch-all MCP mount at "/", or the mount shadows it and
    # /metrics 404s while looking correctly configured.
    @app.get("/metrics", include_in_schema=False)
    def metrics_endpoint():
        from fastapi.responses import Response

        body, content_type = metrics.render()
        return Response(content=body, media_type=content_type)

    app.mount("/", mcp.streamable_http_app())
    return app


def main(argv=None) -> None:
    import uvicorn
    settings = get_settings()
    uvicorn.run(build_http_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()

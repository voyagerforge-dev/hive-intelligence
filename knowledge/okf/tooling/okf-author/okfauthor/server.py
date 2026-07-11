"""Entrypoint: okf-author HTTP MCP server (write-only)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from okfauthor.config import get_settings
from okfauthor.mcp_app import build_mcp


def _gh_factory(settings):
    from okfauthor.github_client import GitHubIssueClient
    return lambda: GitHubIssueClient(settings.github_api, settings.github_repo, settings.github_token)


def build_http_app(settings):
    from fastapi import FastAPI

    mcp = build_mcp(settings, _gh_factory(settings))

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="OKF Author", lifespan=lifespan)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    app.mount("/", mcp.streamable_http_app())
    return app


def main(argv=None) -> None:
    import uvicorn
    settings = get_settings()
    uvicorn.run(build_http_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()

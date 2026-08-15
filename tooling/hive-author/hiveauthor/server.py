"""Entrypoint: hive-author HTTP MCP server (write-only)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from hiveauthor import metrics
from hiveauthor.config import get_settings
from hiveauthor.mcp_app import build_mcp


CLIENTS = {"forgejo": "ForgejoIssueClient", "github": "GitHubIssueClient"}


def _token_source(settings):
    """A string, or a callable that re-reads a file.

    The file exists for GitHub App installation tokens, which last an hour while this
    server runs for days. Read per submission rather than captured: a token held from
    startup works all afternoon and then 401s.
    """
    if not settings.forge_token_file:
        return settings.forge_token

    path = settings.forge_token_file

    def read() -> str:
        with open(path) as fh:
            return fh.read().strip()

    # Read once now so a path that never existed fails at startup. A file that is
    # missing later is a different problem and surfaces at the submission, which is the
    # best that can be done for a credential minted by something else.
    try:
        read()
    except OSError as e:
        raise RuntimeError(f"hive-author: forge_token_file is unreadable: {e}") from e
    return read


def _issue_client_factory(settings):
    import hiveauthor.issue_client as ic

    missing = [n for n in ("forge_api", "forge_repo", "forge_kind") if not getattr(settings, n)]
    if not settings.forge_token and not settings.forge_token_file:
        missing.append("forge_token")
    if missing:
        # Refuse to start rather than serve a client that builds `/repos//issues` and
        # 404s every submission while reporting success. That exact gap ran unnoticed
        # from deployment until 2026-08-11.
        raise RuntimeError(f"hive-author is not configured: missing {', '.join(missing)}")
    if settings.forge_kind not in CLIENTS:
        raise RuntimeError(
            f"hive-author: forge_kind must be one of {', '.join(sorted(CLIENTS))}, "
            f"got {settings.forge_kind!r}"
        )

    cls = getattr(ic, CLIENTS[settings.forge_kind])
    token = _token_source(settings)
    return lambda: cls(settings.forge_api, settings.forge_repo, token)


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

"""Entrypoint: `hiveserve serve --stdio` (MCP over stdio) or `--http` (REST + mounted MCP)."""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager

from hiveserve import ledger
from hiveserve.app import build_rest_router
from hiveserve.config import get_settings
from hiveserve.mcp_app import build_mcp
from hiveserve.metrics import PrometheusHTTPMiddleware, register_content_collector


def _choose_transport(http_flag: bool, stdio_flag: bool, settings) -> str:
    if http_flag:
        return "http"
    if stdio_flag:
        return "stdio"
    return settings.transport


def _conn_factory(settings):
    """The ledger connection factory.

    Fails here rather than at the first tool call. The SQLite version built a path and
    created the file if it was missing, so a deployment pointed at the wrong directory
    came up healthy and served an empty ledger to whoever asked. There is no equivalent
    accident with a DSN: either it is set and reachable, or this refuses to start.
    """
    if not settings.ledger_dsn:
        raise RuntimeError(
            "LEDGER_DSN is not set. The ledger is Postgres since 2026-08-19; there is no "
            "file fallback, because falling back is how an empty ledger gets served as if "
            "it were the real one."
        )
    dsn = settings.ledger_dsn
    return lambda: ledger.session(dsn)


def build_http_app(settings):
    from fastapi import FastAPI

    mcp = build_mcp(settings, _conn_factory(settings))

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="OKF Serving Layer", lifespan=lifespan)
    app.include_router(build_rest_router(settings))
    app.mount("/", mcp.streamable_http_app())
    try:
        register_content_collector(settings.concepts_dir, settings.clients_dir,
                                   _conn_factory(settings))
    except ValueError:
        pass  # already registered (e.g. a second build_http_app in the same process/test run)
    return PrometheusHTTPMiddleware(app)


def main(argv=None) -> None:
    """Start the server, or refuse in one line naming the setting that is wrong.

    A startup refusal here is always a configuration mistake, and its message already
    says which setting and why. Letting the exception escape printed that sentence under
    fifteen frames of uvicorn and psycopg internals, which add nothing a reader can act
    on and make a one-setting mistake read as a crash. `getting-started.md` documents the
    single line, so this is also the guide keeping its word.

    `SystemExit` - what `require_dir` raises - already prints its message without a
    traceback, so it is left alone rather than re-wrapped.
    """
    try:
        _main(argv)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None


def _main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="hiveserve")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve")
    grp = serve.add_mutually_exclusive_group()
    grp.add_argument("--stdio", action="store_true")
    grp.add_argument("--http", action="store_true")
    args = parser.parse_args(argv)
    settings = get_settings()
    transport = _choose_transport(args.http, args.stdio, settings)
    if transport == "http":
        import uvicorn

        uvicorn.run(build_http_app(settings), host=settings.host, port=settings.port)
    else:
        build_mcp(settings, _conn_factory(settings)).run(transport="stdio")


if __name__ == "__main__":
    main()

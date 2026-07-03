"""Entrypoint: `okfserve serve --stdio` (MCP over stdio) or `--http` (REST + mounted MCP)."""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
from pathlib import Path

from okfserve import ledger
from okfserve.app import build_rest_router
from okfserve.config import get_settings
from okfserve.mcp_app import build_mcp


def _choose_transport(http_flag: bool, stdio_flag: bool, settings) -> str:
    if http_flag:
        return "http"
    if stdio_flag:
        return "stdio"
    return settings.transport


def _conn_factory(settings):
    db = Path(settings.okf_data_dir) / "objectives.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    return lambda: ledger.session(db)


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
    return app


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="okfserve")
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

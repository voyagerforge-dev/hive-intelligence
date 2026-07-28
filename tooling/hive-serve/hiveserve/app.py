"""REST/OpenAPI door over the OKF resolver."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict

from hiveserve import metrics, tools
from hiveserve.resolver import get_card


class ResolveRequest(BaseModel):
    # Reject unknown fields rather than ignoring them. The REST door serves shared
    # knowledge only: client-scoped memory and issue cards are reachable through MCP,
    # which carries an identity, and not here. Without this, a caller passing
    # `client` gets a 200 and a shared-only answer, and has no way to tell that the
    # scoping they asked for was never applied.
    model_config = ConfigDict(extra="forbid")

    ids: list[str]
    depth: int = 1


def build_rest_router(settings) -> APIRouter:
    router = APIRouter()
    cdir = settings.concepts_dir

    @router.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @router.get("/metrics")
    def prometheus_metrics() -> PlainTextResponse:
        body, content_type = metrics.render()
        return PlainTextResponse(body, media_type=content_type)

    @router.get("/concepts")
    def concepts(product: str | None = None) -> list[dict]:
        return tools.list_concepts(cdir, product=product)

    @router.get("/find_concepts")
    def find_concepts(q: str, product: str | None = None, limit: int = 20) -> list[dict]:
        return tools.find_concepts(cdir, q, product=product, limit=limit)

    @router.get("/card/{card_id:path}")
    def card(card_id: str) -> dict:
        text = get_card(cdir, card_id)
        if text is None:
            raise HTTPException(status_code=404, detail=f"no card '{card_id}'")
        return {"id": card_id, "markdown": text}

    @router.post("/resolve")
    def resolve(req: ResolveRequest) -> dict:
        return tools.resolve_cards(cdir, req.ids, depth=req.depth,
                                   max_cards=settings.max_cards, max_chars=settings.max_chars)

    return router

"""REST/OpenAPI door over the OKF resolver."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from okfserve import tools
from okfserve.resolver import get_card


class ResolveRequest(BaseModel):
    ids: list[str]
    depth: int = 1


def build_rest_router(settings) -> APIRouter:
    router = APIRouter()
    cdir = settings.concepts_dir

    @router.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @router.get("/concepts")
    def concepts() -> list[dict]:
        return tools.list_concepts(cdir)

    @router.get("/card/{card_id}")
    def card(card_id: str) -> dict:
        text = get_card(cdir, card_id)
        if text is None:
            raise HTTPException(status_code=404, detail=f"no card '{card_id}'")
        return {"id": card_id, "markdown": text}

    @router.post("/resolve")
    def resolve(req: ResolveRequest) -> dict:
        return tools.resolve_cards(cdir, req.ids, depth=req.depth)

    return router

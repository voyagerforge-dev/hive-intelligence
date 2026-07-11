"""MCP door for okf-author: two hard-separated write tools that file GitHub issues into the
existing OKF Actions. No corpus/ledger read; only issues:write via the injected client."""
from __future__ import annotations

from mcp.server.fastmcp import Context, FastMCP

from okfauthor import submissions
from okfauthor.identity import resolve_owner


def owner_from_ctx(ctx: Context, settings) -> str:
    req = getattr(ctx.request_context, "request", None)
    headers = getattr(req, "headers", None)
    return resolve_owner(headers, settings)


def build_mcp(settings, gh_factory) -> FastMCP:
    mcp = FastMCP("okf-author", stateless_http=True, host=settings.host, port=settings.port)

    @mcp.tool()
    def submit_memory_promotion(client: str, product: str, title: str, lesson: str, ctx: Context,
                                context: str = "", platform: str = "",
                                related: list[str] | None = None,
                                citations: list[str] | None = None) -> dict:
        """File a CLIENT-scoped memory-promotion issue (requires a client; never touches core
        knowledge). Opens an okf-memory issue for CODEOWNER approve-label + Action."""
        owner = owner_from_ctx(ctx, settings)
        try:
            sub = submissions.build_memory_submission(
                owner=owner, client=client, product=product, title=title, lesson=lesson,
                context=context, platform=platform, related=related, citations=citations)
        except ValueError as e:
            return {"error": str(e)}
        return gh_factory().create_issue(**sub)

    @mcp.tool()
    def submit_correction(target_concept_id: str, corrected_fact: str, rationale: str, ctx: Context,
                          citations: list[str] | None = None,
                          supersedes: list[str] | None = None) -> dict:
        """File a CORE-knowledge correction issue against a concept id (never client-scoped).
        Opens an okf-correction issue for CODEOWNER approve-label + Action."""
        owner = owner_from_ctx(ctx, settings)
        sub = submissions.build_correction_submission(
            owner=owner, target_concept_id=target_concept_id, corrected_fact=corrected_fact,
            rationale=rationale, citations=citations, supersedes=supersedes)
        return gh_factory().create_issue(**sub)

    return mcp

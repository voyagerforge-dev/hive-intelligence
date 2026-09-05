"""MCP door: read + ledger tools over one resolver+ledger core."""
from __future__ import annotations

from hivegen.corpus import require_dir
from mcp.server.fastmcp import Context, FastMCP

from hiveserve import dbobjects, ledger, tools
from hiveserve.identity import resolve_owner
from hiveserve.metrics import track_tool


def owner_from_ctx(ctx: Context, settings) -> str:
    req = getattr(ctx.request_context, "request", None)
    headers = getattr(req, "headers", None)
    return resolve_owner(headers, settings)


def build_mcp(settings, conn_factory) -> FastMCP:
    mcp = FastMCP("okf", stateless_http=True, host=settings.host, port=settings.port)
    # Refuse here rather than on the first tool call, the same reason LEDGER_DSN does.
    # An unset CONCEPTS_DIR is Path("."), which exists, so the catalogue used to be built
    # out of whatever markdown sat in the working directory and served as concept cards.
    cdir = require_dir(settings.concepts_dir, setting="CONCEPTS_DIR",
                       what="the concept cards this server serves")
    cldir = settings.clients_dir

    @mcp.tool()
    @track_tool("list_concepts")
    def list_concepts(client: str | None = None, product: str | None = None) -> list[dict]:
        """List selectable OKF cards, lean (id + title, no description). Optionally scope by
        `product`, or by `client` to include that client's memory. For a topic or subject
        question, prefer `find_concepts` - listing the whole catalogue is large."""
        return tools.list_concepts(cdir, cldir, client=client, product=product)

    @mcp.tool()
    @track_tool("find_concepts")
    def find_concepts(query: str, product: str | None = None, limit: int = 20,
                      client: str | None = None) -> list[dict]:
        """Search concept cards by name or by what they mean, and get back a small ranked
        set with descriptions. Use this for any topic or subject question ("explain X",
        "how does Y work") instead of listing the whole catalogue; then load the ids you
        want with `resolve` / `get_card`. Optionally scope by `product`, or by `client` to
        search that client's own memory and issue cards alongside the shared ones."""
        return tools.find_concepts(cdir, query, clients_dir=cldir, product=product,
                                   limit=limit, client=client)

    @mcp.tool()
    @track_tool("get_card")
    def get_card(card_id: str) -> str:
        """Return the full markdown of one OKF card (concept or client memory) by id."""
        return tools.get_card_text(cdir, card_id, cldir)

    @mcp.tool()
    @track_tool("resolve")
    def resolve(ids: list[str], depth: int = 1, client: str | None = None) -> dict:
        """Load cards by id plus cross-linked neighbours; `client` scopes client memory
        (hard-isolated)."""
        return tools.resolve_cards(cdir, ids, depth=depth, max_cards=settings.max_cards,
                                   max_chars=settings.max_chars, clients_dir=cldir,
                                   client=client)

    @mcp.tool()
    @track_tool("find_db_objects")
    def find_db_objects(query: str, kind: str | None = None, module: str | None = None,
                        limit: int = 20) -> list[dict]:
        """Search database objects (tables, packages, procedures, …) by name or by what
        they mean. Use for schema-level questions (specific tables/columns/keys/logic); then
        load the returned ids with `resolve`/`get_card`."""
        return dbobjects.search(cdir, query, kind=kind, module=module, limit=limit)

    @mcp.tool()
    @track_tool("start_objective")
    def start_objective(mode: str, goal: str, ctx: Context,
                        external_ref: dict | None = None) -> dict:
        """Start a tracked objective (mode: investigate|implement|learn)."""
        with conn_factory() as conn:
            return ledger.start_objective(conn, owner=owner_from_ctx(ctx, settings),
                                          mode=mode, goal=goal, external_ref=external_ref)

    @mcp.tool()
    @track_tool("list_objectives")
    def list_objectives(ctx: Context, status: str | None = None) -> list[dict]:
        """List the caller's objectives, optionally filtered by status."""
        with conn_factory() as conn:
            return ledger.list_objectives(conn, owner=owner_from_ctx(ctx, settings), status=status)

    @mcp.tool()
    @track_tool("get_objective")
    def get_objective(objective_id: str, ctx: Context) -> dict | None:
        """Rehydrate one objective with its full entry log."""
        with conn_factory() as conn:
            return ledger.get_objective(conn, owner=owner_from_ctx(ctx, settings),
                                        objective_id=objective_id)

    @mcp.tool()
    @track_tool("append_entry")
    def append_entry(objective_id: str, kind: str, content: str, ctx: Context,
                     card_ids: list[str] | None = None) -> dict | None:
        """Append an entry (plan|step|finding|decision|quiz_result|note) to an objective."""
        with conn_factory() as conn:
            return ledger.append_entry(conn, owner=owner_from_ctx(ctx, settings),
                                       objective_id=objective_id, kind=kind,
                                       content=content, card_ids=card_ids)

    @mcp.tool()
    @track_tool("set_status")
    def set_status(objective_id: str, status: str, ctx: Context) -> dict | None:
        """Set an objective's status (open|active|resolved|done)."""
        with conn_factory() as conn:
            return ledger.set_status(conn, owner=owner_from_ctx(ctx, settings),
                                     objective_id=objective_id, status=status)

    @mcp.tool()
    @track_tool("record_quiz_result")
    def record_quiz_result(objective_id: str, concept_id: str, score: float, ctx: Context,
                           detail: str | None = None) -> dict | None:
        """Record a learning quiz result against an objective."""
        with conn_factory() as conn:
            return ledger.record_quiz_result(conn, owner=owner_from_ctx(ctx, settings),
                                             objective_id=objective_id, concept_id=concept_id,
                                             score=score, detail=detail)

    @mcp.tool()
    @track_tool("remember")
    def remember(text: str, ctx: Context, tags: list[str] | None = None,
                 card_ids: list[str] | None = None, external_ref: dict | None = None,
                 client: str | None = None) -> dict:
        """Save a private personal memory (owner-scoped; optional client tag)."""
        with conn_factory() as conn:
            return ledger.remember(conn, owner=owner_from_ctx(ctx, settings), text=text, tags=tags,
                                   card_ids=card_ids, external_ref=external_ref, client=client)

    @mcp.tool()
    @track_tool("recall")
    def recall(ctx: Context, query: str | None = None, tags: list[str] | None = None,
               card_id: str | None = None, client: str | None = None,
               limit: int = 20) -> list[dict]:
        """Recall your personal memories by substring/tag/card/client filter."""
        with conn_factory() as conn:
            return ledger.recall(conn, owner=owner_from_ctx(ctx, settings), query=query,
                                 tags=tags, card_id=card_id, client=client, limit=limit)

    @mcp.tool()
    @track_tool("forget")
    def forget(memory_id: str, ctx: Context) -> dict:
        """Delete one of your personal memories."""
        with conn_factory() as conn:
            return {"deleted": ledger.forget(conn, owner=owner_from_ctx(ctx, settings),
                                             memory_id=memory_id)}

    @mcp.tool()
    @track_tool("promote")
    def promote(memory_id: str, ctx: Context) -> dict:
        """Prepare a personal memory for client-scoped promotion (requires a client)."""
        with conn_factory() as conn:
            return ledger.promote_memory(conn, owner=owner_from_ctx(ctx, settings),
                                         memory_id=memory_id)

    return mcp

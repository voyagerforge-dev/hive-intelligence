# OKF tooling - hive-serve (`hiveserve`)

*Stage 3 of the OKF pipeline: serves the cards to Claude and tools over a REST door and an MCP door, LLM-free, over a per-owner SQLite work ledger. Conceptual model in [architecture/pipeline.md §5](../architecture/pipeline.md#5-stage-3-serving-hive-serve).*

**Tooling reference:** [Hub](README.md) · [hive-prep](hive-prep.md) · [hive-gen](hive-gen.md) · **hive-serve** · [hive-dbparse](hive-dbparse.md) · [hive-author](hive-author.md) · [hive-zendesk](hive-zendesk.md) · [Architecture & Concepts](../architecture/pipeline.md)

hive-serve is the runtime that hands OKF cards to an agent. It has **one core** (a no-RAG `resolver` over git-tracked markdown cards, plus a SQLite `ledger` of per-owner objectives and personal memory), reached through **two doors** (a FastAPI REST/OpenAPI router in `app.py` and an MCP server in `mcp_app.py`, both mounted in one ASGI app), backed by **two stores** (the card corpus on disk and `objectives.db`). The serving path is deliberately LLM-free: retrieval is direct id lookup plus cross-link traversal, and search is substring/token matching. A separate **offline eval harness** (`agent`/`eval`/`run_eval`, which does call an LLM through `hivegen`) scores the retrieval logic against labelled Q&A sets but is never on the serving path.

## Module index
| Module | Purpose |
|---|---|
| `resolver.py` | Core, no-RAG retrieval: card-id → file mapping, corpus index, cross-link BFS with regime/client isolation guards, corrections co-pull. |
| `tools.py` | Transport-agnostic thin wrappers over the resolver (`list_concepts`, `get_card_text`, `resolve_cards`) shared by both doors. |
| `dbobjects.py` | Core, LLM-free keyword search over per-product WMOS db-object manifests; backs the on-demand `find_db_objects` tool. |
| `ledger.py` | Core SQLite ledger: per-owner objectives + entries and personal memory, with enum validation and owner-scoped access. |
| `identity.py` | Resolve the caller's owner id from a trusted proxy header, else the configured default. |
| `app.py` | REST/OpenAPI door: `/healthz`, `/metrics`, `/concepts`, `/card/{id}`, `/resolve`. |
| `mcp_app.py` | MCP door: 14 read + ledger tools over the shared core, each metrics-wrapped; no prompts. |
| `server.py` | Entrypoint / CLI (`hiveserve serve --stdio|--http`); wires config, ledger connection factory, and the mounted app. |
| `config.py` | Typed env/`.env`-backed settings (`pydantic-settings`). |
| `metrics.py` | Prometheus registry, HTTP + MCP-tool instrumentation, TTL-cached corpus/ledger content gauges. |
| `index.py` | Eval/authoring format pass: emit `index.md` and render `related` frontmatter into inline cross-links. Not on the serving path. |
| `agent.py` | Offline: grounded-Q&A agent (LLM select + answer) over a resolved bundle. Eval-only. |
| `eval.py` | Offline: score selection/regime/product/version/correction/memory and LLM-judge answers. Eval-only. |
| `run_eval.py` | Offline: live entrypoint that runs the agent over a labelled QA set via Bifrost. Eval-only. |

## Modules

### `resolver.py`
**Purpose.** The no-RAG retrieval core: build a lightweight index of cards, map ids to files, load a card, and resolve a set of ids into a bundle by following `related` cross-links one hop (by default), with scope/regime isolation and correction co-pull.

**Key logic.**
- `card_path(concepts_dir, card_id, clients_dir=None)` maps a card id to a file. Ids starting with `clients/` resolve under `clients_dir` (stripping the `clients/` prefix); everything else resolves under `concepts_dir`. After resolving, it checks the result is still inside its base directory (path-escape / traversal guard) and returns `None` if the file is missing or escapes.
- `load_index(concepts_dir, clients_dir=None)` walks `*.md` under the concepts dir, skipping `index.md`/`log.md`. **It excludes the db-object tier**: any card whose relative path contains a `db` segment before the filename (`concepts/<product>/db/**`) is skipped, because those schema-level rows are served on demand via `find_db_objects`, not through the concept index. Each surviving card yields a dict of frontmatter facets (`title`, `description`, `regime`, `type`, `version`, `product`, `corrects`, `status`; `client=None` for concepts). If `clients_dir` is given, it also indexes **only** `<client>/memory/<slug>.md` paths as `type: memory` with `client` set from the path.
- `corrections_by_target(index)` builds a map of concept id → active correction ids, where active means `type == correction` and `status == approved`.
- `resolve(...)` is a BFS over ids. The seed frontier is filtered by `in_scope` - a client-scoped card (`clients/<client>/...`) is admitted only when its client equals the caller's `client` arg (core cards are always in scope). It then expands `related` links up to `depth` levels, honoring `max_cards` (excess ids are recorded in `dropped`). Two guards apply during expansion and are deliberately **not** marked `seen`, so a different path could still reach the card legitimately: the **cross-regime guard** skips a neighbour whose `regime` differs from the parent's, and the **cross-client / out-of-scope memory guard** skips a client card whose client is not the caller's. Broken `related` links are tolerated. An optional `max_chars` budget trims the tail (always keeping at least the first card). Finally it **co-pulls corrections**: for every selected card it appends any approved correction targeting it (deduped, existence-checked), and returns `{card_ids, bundle, dropped, corrections}` where `bundle` is the concatenated markdown joined by `\n\n---\n\n`.

**Inputs → outputs.** Directory paths + a list of card ids → a dict with the ordered id list, the concatenated markdown bundle, dropped ids, and the appended correction ids.

**Dependencies.** internal: none (leaf of the core). external: `pyyaml` (frontmatter parsing).

**Invoked / deployed.** Called by `tools.py`, `metrics.py` (`load_index` for content gauges), `index.py`, and the eval `agent.py`. On the serving path in the container.

### `tools.py`
**Purpose.** Transport-agnostic read tools so REST and MCP call identical logic.

**Key logic.**
- `list_concepts(concepts_dir, clients_dir=None, client=None)` returns the index with `type == correction` filtered out, and memory cards filtered out unless `client` is set and matches (concepts are always included). Correction cards never appear in the selectable list - they ride along via the resolver.
- `get_card_text(...)` returns the card markdown or a `"No card found with id '<id>'."` string (never `None`, for a clean tool response).
- `resolve_cards(...)` forwards to `resolver.resolve` with `depth`/`max_cards`/`max_chars`/`clients_dir`/`client`.

**Inputs → outputs.** Same as the resolver, minus path-escape handling (delegated).

**Dependencies.** internal: `resolver`. external: none.

**Invoked / deployed.** Both doors. On the serving path.

### `dbobjects.py`
**Purpose.** LLM-free keyword search over the WMOS db-object manifests the resolver excludes from the concept index; the only path back to those schema-level rows, exposed as the `find_db_objects` MCP tool.

**Key logic.**
- `_load_rows(concepts_dir)` reads every `<product>/db/manifest.jsonl` (one JSON object per line: `{id, kind, module, product, title, description, tags}`) produced by hive-dbparse.
- `search(concepts_dir, query, kind=None, module=None, limit=20)` lowercases and tokenizes the query, optionally filters rows by exact `kind` and `module`, and scores each remaining row by `_score` - the count of query tokens found as substrings in a lowercased haystack of `title + description + id + tags`. Rows with score 0 are dropped; hits sort by descending score then id, and the top `limit` return a trimmed projection (`id`, `kind`, `module`, `product`, `title`, `description`). No embeddings, no network - matching mirrors `ledger.recall`. An empty query returns `[]`.

**Inputs → outputs.** Concepts dir + query (+ optional filters) → ranked list of db-object stubs; the caller then loads full bodies with `resolve`/`get_card`.

**Dependencies.** internal: none. external: stdlib `json` only.

**Invoked / deployed.** `mcp_app.find_db_objects`. On the serving path (MCP door only).

### `ledger.py`
**Purpose.** The stateful half of the core: a SQLite store of per-owner objectives (with an append-only entry log) and per-owner personal memory, over which the MCP tools drive tracked work streams.

**Key logic.**
- **Schema** (`init_db`, idempotent `CREATE ... IF NOT EXISTS`): `objective(id, owner, mode, goal, status, external_ref, visibility, created_at, updated_at)`, `entry(id, objective_id→objective ON DELETE CASCADE, kind, content, card_ids, created_at)`, and `memory(id, owner, text, client, tags, card_ids, external_ref, visibility, created_at, updated_at)`. Connections set `journal_mode=WAL` and `foreign_keys=ON`; owner and objective_id are indexed. `session(path)` is a context manager yielding a connection.
- **Owner scoping is structural, never a caller-supplied filter argument.** Every read/write threads `owner` and every objective/memory statement carries `WHERE ... owner=?` (`_owned` gates objective access; `get_memory`/`forget`/`set_memory_visibility` gate memory). The MCP layer always derives `owner` from identity (see below), so one caller can never read or mutate another's rows.
- **Enum validation** guards all state: `mode ∈ {investigate, implement, learn}`, `status ∈ {open, active, resolved, done}`, entry `kind ∈ {plan, step, finding, decision, quiz_result, note}`, memory `visibility ∈ {private, promotion_requested}`. A bad value raises `ValueError`.
- Objective ops: `start_objective` (defaults `status=open`, `visibility=private`), `list_objectives` (optional status filter, newest-first), `get_objective` (rehydrates with its ordered entry log), `append_entry` (also bumps the objective's `updated_at`), `set_status`, `record_quiz_result` (a typed `quiz_result` entry carrying `{concept_id, score, detail}` and citing the concept). Objective/entry mutations return `None` when the objective isn't owned by the caller.
- Memory ops: `remember` (owner-scoped, optional `client` tag, `tags`, `card_ids`, `external_ref`; `visibility=private`), `get_memory`, `recall` (in-Python filter over the owner's rows by `client`, `card_id` membership, tag-subset, and case-insensitive substring over text/tags - same matching style as `dbobjects`), `forget` (returns whether a row was deleted). `promote_memory` is the **guarded** promotion prep: it requires a non-empty `client`, flips visibility to `promotion_requested`, and returns `{memory_id, record}` where `promotion_record` builds the neutral record consumed downstream by `hivegen.memory`; on failure it returns `{"error": ...}`.

**Inputs → outputs.** A connection + keyword-only `owner` and operation args → dict rows / lists / booleans.

**Dependencies.** internal: none. external: stdlib `sqlite3`, `json`, `uuid`, `datetime`.

**Invoked / deployed.** All ledger MCP tools via `server._conn_factory` (a `session` over `<OKF_DATA_DIR>/objectives.db`); `metrics.content_samples` counts its rows. On the serving path.

### `identity.py`
**Purpose.** Trusted-header owner resolution: turn the edge-injected identity header into the ledger `owner`.

**Key logic.** `resolve_owner(headers, settings)` reads `settings.identity_header` from the request headers. It tries a direct `.get(name)` first (works for framework header objects), and on miss rebuilds a lowercased-key view of the dict and retries with `name.lower()` (so plain dicts and case differences still resolve). Any header access error falls back cleanly. If no value is found it returns `settings.okf_default_owner`. Identity is therefore **trusted from the proxy** - hive-serve does no auth of its own; it assumes the edge (Cloudflare Access) authenticated the user and stamped the header.

**Inputs → outputs.** Request headers + settings → an owner string (never empty).

**Dependencies.** internal: none. external: none.

**Invoked / deployed.** `mcp_app.owner_from_ctx`. On the serving path.

### `mcp_app.py`
**Purpose.** The MCP door - a `FastMCP` server exposing the read + ledger core as tools. **14 tools, no prompts** (the former persona prompts were retired; personas now live in the OKF Cowork plugin).

**Key logic.**
- `build_mcp(settings, conn_factory)` constructs `FastMCP("okf", stateless_http=True, host, port)` and registers each tool with `@mcp.tool()` (schema derived from the signature) wrapped by `@track_tool("<name>")` for metrics.
- `owner_from_ctx(ctx, settings)` pulls headers off the MCP request context and calls `resolve_owner`; every ledger tool derives `owner` this way - it is never a tool parameter.
- The 14 tools: **read** - `list_concepts`, `get_card`, `resolve`, `find_db_objects`; **objectives** - `start_objective`, `list_objectives`, `get_objective`, `append_entry`, `set_status`, `record_quiz_result`; **memory** - `remember`, `recall`, `forget`, `promote`. Read tools take a corpus dir from settings; ledger tools open a connection via `conn_factory()` per call. `resolve`/`list_concepts` accept a `client` arg that scopes client memory (hard-isolated in the resolver).

**Inputs → outputs.** MCP JSON-RPC tool calls → tool results (dicts/lists/strings). Errors propagate (and are counted `outcome=error`).

**Dependencies.** internal: `tools`, `dbobjects`, `ledger`, `identity`, `metrics`. external: `mcp` (FastMCP).

**Invoked / deployed.** Mounted at `/mcp` by `server.build_http_app` (streamable HTTP) and run directly for `--stdio`. On the serving path.

### `app.py`
**Purpose.** The REST/OpenAPI door - a FastAPI `APIRouter` over the read core (no ledger tools; the stateful surface is MCP-only).

**Key logic.** `build_rest_router(settings)` exposes `GET /healthz` (`{"ok": true}`), `GET /metrics` (Prometheus text via `metrics.render()`), `GET /concepts` (`tools.list_concepts`), `GET /card/{card_id:path}` (full markdown or 404), and `POST /resolve` (`ResolveRequest{ids, depth}` → `tools.resolve_cards` bounded by `settings.max_cards`/`max_chars`). The REST door does not pass `clients_dir`/`client`, so it serves the core corpus only.

**Inputs → outputs.** HTTP → JSON (or plaintext for `/metrics`).

**Dependencies.** internal: `metrics`, `tools`, `resolver`. external: `fastapi`, `pydantic`.

**Invoked / deployed.** Included by `server.build_http_app`. On the serving path (HTTP transport).

### `server.py`
**Purpose.** Entrypoint and transport wiring. Concise: `main()` parses `hiveserve serve` with a mutually exclusive `--stdio`/`--http`; `_choose_transport` falls back to `settings.transport` when neither flag is given. `--http` runs uvicorn over `build_http_app`; otherwise it runs the MCP server over stdio. `_conn_factory(settings)` returns a `lambda: ledger.session(<OKF_DATA_DIR>/objectives.db)` (creating the parent dir). `build_http_app` builds the MCP server, mounts it at `/` (streamable HTTP) alongside the REST router in a `FastAPI` app with a lifespan that runs the MCP session manager, registers the content collector (tolerating a duplicate-registration `ValueError`), and wraps the whole app in `PrometheusHTTPMiddleware`.

**Dependencies.** internal: `ledger`, `app`, `config`, `mcp_app`, `metrics`. external: `fastapi`, `uvicorn`, `argparse`.

### `config.py`
**Purpose.** Typed settings. Concise: `Settings(BaseSettings)` reads env vars / `.env` (`extra="ignore"`), `get_settings()` is `lru_cache`d. Serving-relevant fields: `concepts_dir`, `clients_dir`, `okf_data_dir`, `host`, `port`, `transport`, `max_cards` (8), `max_chars` (80000), `resolve_depth` (1), `identity_header` (default `x-forwarded-email`), `okf_default_owner` (`local-operator`). Eval-only fields: `bifrost_base`/`bifrost_api_key`/`select_model`/`answer_model`/`judge_model`/`bifrost_timeout_s`. Env names are the upper-cased field names (e.g. `CONCEPTS_DIR`, `IDENTITY_HEADER`), so the Dockerfile/`.env` overrides bind directly.

### `metrics.py`
**Purpose.** Prometheus instrumentation on one custom `CollectorRegistry` (no `client` label anywhere - a deliberate cardinality rule). Concise:
- Counters/histograms: `http_requests_total{endpoint,method,status}`, `http_request_duration_seconds{endpoint,method}`, `mcp_tool_calls_total{tool,outcome}`, `mcp_tool_duration_seconds{tool}`.
- `track_tool(name)` is the signature-preserving decorator each MCP tool wears; it times the call, sets `outcome=ok`/`error` (re-raising), and increments the counters.
- `PrometheusHTTPMiddleware` is pure-ASGI; it only labels the known REST endpoints (`/healthz`, `/concepts`, `/resolve`, `/card/{id}`) and skips everything else - the `/mcp` mount (tool usage is a tool-layer metric) and, deliberately, `/metrics` itself. It reads only the response-start message, so it never buffers a streaming MCP response.
- `content_samples` + `ContentCollector` expose TTL-cached (30s) gauges `okf_corpus_cards{product,regime}` (from `load_index`) and `okf_ledger_rows{table}` (objective/memory counts). The collector degrades to last-known-good / empty on a sampling error rather than failing the scrape.
- `render()` returns the exposition body + content type for the `/metrics` route.

### `index.py`
**Purpose.** OKF format pass (authoring/eval helper, **not** on the serving path). Concise: `apply_format_pass(concepts_dir)` writes `index.md` (a progressive-disclosure link list from `load_index`) and rewrites each card's `## Related` section from its `related` frontmatter into inline markdown links. A precise regex replaces only an exact `## Related` heading, never a differently-named section. Returns the index name and the list of updated cards.

### `agent.py`, `eval.py`, `run_eval.py` - offline eval harness (not on the serving path)
These import `hivegen.llm` and call an LLM; they exist to measure the LLM-free retrieval core, never to serve it.
- `agent.py` - `answer_question(...)` runs a two-model grounded-Q&A flow: `select_ids` asks a select-LLM to pick card ids from the index (with strict product/regime/version/client-memory selection rules baked into the system prompt), `resolve` builds the bundle (with correction co-pull), then an answer-LLM answers using only the bundle. A `ceiling` mode selects all concepts to measure the retrieval ceiling.
- `eval.py` - `run_eval(...)` scores each labelled item along selection hit, regime, product, version, correction, and memory/cross-client dimensions, plus an LLM judge for grounded/correct, and aggregates.
- `run_eval.py` - CLI that builds three `BifrostChat` models from `config` and runs `run_eval` over a JSONL QA set (default `data/wave_replen_qa.jsonl`), writing a report under `.eval/`.

## Deployment & runtime
Accurate to `deploy/compose.example.yml` and `deploy/Dockerfile`.

- **Image.** `python:3.12-slim`, non-root user `svc` (uid **1001**), installs both local path deps `hive-gen` (`vf-hive-gen`) and `hive-serve` from the repo checkout (compose `context: ../../..` = repo root). The card corpus is **not** baked in. Default `CMD` is `hiveserve serve --http`.
- **Container / port.** Runs as `hive-serve` on **Host-A** (`hive-host.internal`), published `hive-host.internal:8015 → :8000` (VLAN60-internal). Healthcheck curls `/healthz`.
- **Volumes.** `…/knowledge/okf/concepts → /data/concepts` (ro), `…/knowledge/okf/clients → /data/clients` (ro, client-scoped memory tree), and a writable `…/ledger → /data/ledger` holding `objectives.db` (persists across restarts). A one-shot `okf-ledger-init` service (`alpine`, as root) `chown`s the ledger dir to `1001:1001` on every `up` so the `svc` uid can open the DB; hive-serve `depends_on` its successful completion.
- **Env.** Set in the image: `TRANSPORT=http`, `HOST=0.0.0.0`, `PORT=8000`, `CONCEPTS_DIR=/data/concepts`, `CLIENTS_DIR=/data/clients`, `OKF_DATA_DIR=/data/ledger`, `IDENTITY_HEADER=x-vf-identity`, `OKF_DEFAULT_OWNER=local-operator`. Non-secret overrides come from `/srv/hive-serve/.env`. hive-serve is LLM-free and needs no secrets (no SOPS `.env` like the SaaS connectors).
- **Two transports.** `hiveserve serve --stdio` runs the MCP server over stdio (local/desktop use); `hiveserve serve --http` runs uvicorn with the REST router + the MCP server mounted at `/mcp` (the container default). Doors: OpenAPI `/openapi.json` + `/docs`, MCP `/mcp`, health `/healthz`, metrics `/metrics`.
- **Identity gate.** The edge is **Cloudflare Access** (cloudflared on Host-E, routed direct to `hive-host.internal:8015`, bypassing Caddy), gating `hive.example.com` and injecting `Cf-Access-Authenticated-User-Email`. Per the deploy README, `/srv/hive-serve/.env` sets `IDENTITY_HEADER=Cf-Access-Authenticated-User-Email` to consume it (this **overrides** the image default `x-vf-identity`; the code default in `config.py` is a third value, `x-forwarded-email`). Internal LAN callers hit `hive-host.internal:8015` directly and bypass the gate. Live-infra edge/DNS specifics are runbook-owned (verify).
- **Cards freshness.** The corpus is a **sparse, blob-filtered** checkout of `project-hive` (only `knowledge/okf`) mounted read-only. A Windmill runnable `f/example/okf/cards_sync` does `git pull --ff-only` on a 15-minute schedule (verify the exact interval against live Windmill); hive-serve reads cards live.
- **Rebuild rule.** A **content change needs no rebuild or restart** (the pull updates the mounted checkout and the resolver reads it live). A **code change needs an image rebuild** (`docker compose up -d --build`), since the package is installed into the image.
- **Prometheus scrape.** `GET /metrics` (Prometheus text) is scraped by Host-B at `hive-host.internal:8015/metrics` (LAN IP, not localhost). Host-B config is scp-deployed, not git-synced (see deploy README §5).

## Tests
**Posture: fakes-only, no network, no live LLM.** Tests run against a tmp card corpus and a tmp ledger DB; the HTTP-facing tests use FastAPI's `TestClient` (in-process, via the shared `conftest.py` `card_settings`/`card_client` fixtures), and the eval tests use stub LLM objects rather than Bifrost. Roughly **128** test functions across `tests/` (`test_resolver`, `test_tools`, `test_dbobjects`, `test_ledger`, `test_identity`, `test_mcp_app`, `test_rest`, `test_server_http`, `test_metrics`, `test_index`, `test_agent`, `test_eval`, `test_dataset`, `test_config`).

Run:
```bash
cd tooling/hive-serve && uv run pytest -q
```

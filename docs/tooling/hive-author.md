# OKF tooling - hive-author (`hiveauthor`)

*The write-only authoring door: a minimal `issues:write`-only MCP server that files memory-promotion and correction issues, so hive-serve stays keyless. Described in [architecture/pipeline.md - the memory layer](../architecture/pipeline.md#the-memory-layer).*

**Tooling reference:** [Hub](README.md) · [hive-prep](hive-prep.md) · [hive-gen](hive-gen.md) · [hive-serve](hive-serve.md) · [hive-dbparse](hive-dbparse.md) · **hive-author** · [hive-zendesk](hive-zendesk.md) · [Architecture & Concepts](../architecture/pipeline.md)

hive-author is the only OKF component that holds a GitHub credential, and that credential is scoped to `issues:write` only - it can file an issue, never push, merge, or open a PR. It exposes exactly two hard-separated MCP tools: `submit_memory_promotion` (client-scoped, labels `okf-memory`) and `submit_correction` (targets a core concept id, labels `okf-correction`). Each tool builds an issue body whose `### <section>` layout mirrors the `memory.yml` / `correction.yml` Issue Forms exactly, so the same hive-gen Action parsers round-trip the body losslessly; a GitHub Action then opens the PR, but only after a CODEOWNER applies the approve-label. By concentrating the write path here, the read side (hive-serve) can stay keyless and read-only.

## Module index
| Module | Purpose |
|---|---|
| `submissions.py` | Pure issue-body builders; the two hard-separated `build_*` functions and the client-required guard on memory promotion. |
| `github_client.py` | Injectable issue client: `IssueClient` protocol, real `issues:write` `httpx` client, and an in-memory fake for tests. |
| `mcp_app.py` | Builds the `FastMCP` app registering the two write tools; resolves the caller owner and delegates to `submissions` + the injected client. |
| `identity.py` | Resolves the caller's owner id from the trusted CF Access proxy header, else the configured default. |
| `config.py` | Typed `pydantic-settings` config (env / `.env`): GitHub token/repo/api, host/port, identity header, default owner. |
| `server.py` | Entrypoint: wires settings + a real-client factory into `build_mcp`, mounts it under a FastAPI app with `/healthz`, runs uvicorn. |

## Modules

### `submissions.py`
**Purpose.** Pure, side-effect-free builders that turn tool arguments into a GitHub issue payload (`title`, `body`, `labels`). This is where the two authoring paths are structurally kept apart and where round-trip compatibility with the hive-gen Issue-Form parsers is guaranteed.

**Key logic.**
- `_section(label, value)` emits `### <label>\n\n<value or "_No response_">\n`, exactly matching the GitHub Issue Form rendering the hive-gen parsers expect. `_prefix(submitted_by)` prepends `_Submitted via hive-author by <owner>._` when an owner is known.
- `memory_issue_body(...)` lays out the memory sections in Issue-Form order: `Product`, `Client`, `Title`, `The lesson (de-personalised)`, `When it applies`, `Platform (optional)`, `Related concept ids (optional)`, `Citation source files (optional)`. List fields (`related`, `citations`) are newline-joined.
- `correction_issue_body(...)` lays out the correction sections: `Target concept id`, `Corrected fact`, `Rationale`, `Citation source files`, `Supersedes (optional)`.
- `build_memory_submission(...)` is the memory path: it **guards on client** - `if not client or not str(client).strip(): raise ValueError("client_required")` - then normalizes the client to `str(client).strip().lower()`, builds the body, and returns `{"title": f"[memory] {title}", "body": ..., "labels": ["okf-memory"]}`.
- `build_correction_submission(...)` is the correction path: no client, targets a concept id, and returns `{"title": f"[correction] {target_concept_id}", "body": ..., "labels": ["okf-correction"]}`.
- The **hard separation** is by construction: distinct required params (memory needs `client`; correction needs `target_concept_id`), distinct titles (`[memory]` vs `[correction]`), distinct labels (`okf-memory` vs `okf-correction`), and disjoint body sections (`Client` appears only in memory bodies; `Target concept id` only in correction bodies). A memory submission can therefore never reach core knowledge, and a correction is never client-scoped.

**Inputs → outputs.** Keyword-only scalars/lists (e.g. `owner`, `client`, `product`, `title`, `lesson`, ... / `target_concept_id`, `corrected_fact`, `rationale`, ...) → a `dict` payload ready to hand to an `IssueClient.create_issue(**sub)`.

**Dependencies.** internal: none; external: none (pure Python, stdlib only).

**Invoked / deployed.** Called by `mcp_app.py`'s two tool functions. Exercised directly by `tests/test_submissions.py`, which parses the produced bodies back through the real hive-gen parsers.

### `github_client.py`
**Purpose.** The single place that talks to GitHub, and the seam that keeps the credential injectable and testable. It defines the write-only issue interface plus a real and a fake implementation.

**Key logic.**
- `IssueClient` is a `typing.Protocol` with one method: `create_issue(*, title, body, labels) -> dict`. This is the only GitHub capability the server has - no read, no PR, no merge surface exists in the type.
- `GitHubIssueClient(api, repo, token, timeout_s=30)` builds the issues URL `f"{api}/repos/{repo}/issues"` and a `Bearer <token>` header with `Accept: application/vnd.github+json`. `create_issue` does a single `httpx.post` of `{"title", "body", "labels"}`, calls `raise_for_status()`, and returns `{"number": d["number"], "url": d["html_url"]}`. The `token` here is the `issues:write` credential; posting to `/issues` is the only call it ever makes.
- `FakeIssueClient` records each call in `self.calls` and returns a deterministic `{"number": n, "url": "https://github.test/issues/{n}"}`. This is injected in tests so no live token or network is touched.

**Inputs → outputs.** `create_issue(title, body, labels)` → `{"number": int, "url": str}` (issue number and web URL of the filed issue).

**Dependencies.** internal: none; external: `httpx` (real client only); `typing.Protocol`.

**Invoked / deployed.** The real client is constructed lazily by `server.py`'s `_gh_factory`; `mcp_app.py` calls the injected factory per request (`gh_factory().create_issue(**sub)`). The fake backs `tests/test_github_client.py` and `tests/test_mcp_app.py`.

### `mcp_app.py`
**Purpose.** Defines the MCP door: a `FastMCP` app that registers the two write tools, stamps caller identity, and routes each call through `submissions` to the injected GitHub client. It holds no corpus or ledger read path.

**Key logic.**
- `build_mcp(settings, gh_factory)` constructs `FastMCP("hive-author", stateless_http=True, host=settings.host, port=settings.port)`. `gh_factory` is a zero-arg callable returning an `IssueClient`, so the real credential is injected from outside (and swapped for the fake in tests).
- `owner_from_ctx(ctx, settings)` reaches into `ctx.request_context.request.headers` (defensively, via `getattr`) and calls `identity.resolve_owner(headers, settings)` to derive the submitter from the trusted proxy header.
- `submit_memory_promotion(client, product, title, lesson, ctx, context="", platform="", related=None, citations=None)` resolves the owner, calls `submissions.build_memory_submission(...)`, and - crucially - catches the `ValueError("client_required")` guard, returning `{"error": str(e)}` rather than raising to the caller. On success it returns `gh_factory().create_issue(**sub)`. Its docstring documents it as CLIENT-scoped and unable to touch core knowledge.
- `submit_correction(target_concept_id, corrected_fact, rationale, ctx, citations=None, supersedes=None)` resolves the owner, calls `submissions.build_correction_submission(...)`, and files the `okf-correction` issue. Its docstring documents it as a CORE-knowledge correction against a concept id, never client-scoped.
- The two tools mirror the Issue Forms via `submissions`, so a filed issue is directly consumable by the existing hive-gen memory/correction Actions after CODEOWNER approve-label.

**Inputs → outputs.** MCP tool calls (typed args + `Context`) → the `create_issue` result dict `{"number", "url"}`, or `{"error": "client_required"}` for an empty-client memory promotion.

**Dependencies.** internal: `hiveauthor.submissions`, `hiveauthor.identity`; external: `mcp.server.fastmcp` (`FastMCP`, `Context`).

**Invoked / deployed.** Called by `server.py`'s `build_http_app`. `tests/test_mcp_app.py` asserts both tools register and that the build helpers stay hard-separated.

### `identity.py`
**Purpose.** Map an inbound request to an owner id for stamping into the issue body.

**Key logic.** `resolve_owner(headers, settings)` reads `settings.identity_header` (default `cf-access-authenticated-user-email`). It tries `headers.get(name)`; if empty it retries against a lowercased copy of all header keys (case-insensitive fallback), swallowing `AttributeError/TypeError/ValueError`. It returns the header value or, when absent, `settings.okf_default_owner`. This trusts the edge proxy to inject the authenticated email.

**Inputs → outputs.** `(headers, settings)` → owner id string (email or default).

**Dependencies.** internal: none (uses the passed `settings`); external: none.

**Invoked / deployed.** Called from `mcp_app.owner_from_ctx`. Covered by `tests/test_identity.py`.

### `config.py`
**Purpose.** Typed settings for the server, env / `.env` backed.

**Key logic.** `Settings(BaseSettings)` with `env_file=".env", extra="ignore"`. Fields: `github_token` (default empty - the only secret), `github_repo` (default `example-org/project-hive`), `github_api` (`https://api.github.com`), `host` (`127.0.0.1`), `port` (`8000`), `identity_header` (`cf-access-authenticated-user-email`), `okf_default_owner` (`local-operator`). `get_settings()` is `@lru_cache`d. Env vars override the defaults (the container sets `HOST`, `PORT`, `IDENTITY_HEADER`, and `GITHUB_TOKEN` at runtime).

**Inputs → outputs.** Environment / `.env` → a validated `Settings` instance.

**Dependencies.** internal: none; external: `pydantic-settings`.

**Invoked / deployed.** `server.main` calls `get_settings()`. Covered by `tests/test_config.py`.

### `server.py`
**Purpose.** The runnable entrypoint (console script `hiveauthor`) that assembles the HTTP MCP server.

**Key logic.** `_gh_factory(settings)` returns a lambda constructing a `GitHubIssueClient(settings.github_api, settings.github_repo, settings.github_token)` - this is where the live token enters the process, and the import is local so tests never need it. `build_http_app(settings)` builds the MCP app via `build_mcp(settings, _gh_factory(settings))`, wraps a `FastAPI(title="OKF Author")` with a lifespan that runs `mcp.session_manager.run()`, adds `GET /healthz -> {"ok": True}`, and mounts the streamable HTTP MCP app at `/`. `main()` runs it under `uvicorn` on `settings.host` / `settings.port`.

**Inputs → outputs.** Process start → a listening HTTP MCP server (MCP at `/`, health at `/healthz`).

**Dependencies.** internal: `hiveauthor.config`, `hiveauthor.mcp_app`, `hiveauthor.github_client`; external: `fastapi`, `uvicorn`, `mcp`.

**Invoked / deployed.** Container `CMD ["hiveauthor"]` (the `project.scripts` entrypoint). `tests/test_server_http.py` covers the HTTP wiring.

## Deployment & runtime

Accurate to `deploy/compose.example.yml` and `deploy/Dockerfile`:

- **Image / build.** `deploy/Dockerfile` is `python:3.12-slim`, `pip install uv` then `uv pip install --system -e .`, and bakes `ENV HOST=0.0.0.0`, `PORT=8016`, `IDENTITY_HEADER=Cf-Access-Authenticated-User-Email`; `EXPOSE 8016`; `CMD ["hiveauthor"]`. The compose build context is `..` (the package dir), image tagged `hive-author:latest`.
- **Container on Host-A.** Service/container `hive-author`, `restart: unless-stopped`, published on `hive-host.internal:8016:8016` - VLAN60 LAN only (same host=VLAN60 model as hive-serve). `environment` sets `HOST=0.0.0.0` and `PORT=8016`. Healthcheck GETs `http://localhost:8016/healthz` every 30s.
- **Secret, outside the checkout.** `env_file: [/srv/hive-author/hive-author.env]` - the `GITHUB_TOKEN` (`issues:write` only) lives outside the git checkout, decrypted by the operator from SOPS `infra-repo/secrets/host-a/hive-author.enc.env` to `/srv/hive-author/hive-author.env` (mode 600, never committed). The token is the only secret; everything else is plain config.
- **Explicit compose project `name:` (anti-collision).** `deploy/compose.example.yml` pins `name: hive-author`. Both hive-serve and hive-author use a `deploy/` dir, so without this they collide on Compose's default project name - and a `docker compose down --remove-orphans` in one dir would remove the other's containers. If a stale container lands under the wrong project, the README fix is to remove it by name (`docker rm -f hive-author`) then re-`up`, leaving hive-serve untouched.
- **Public edge (CF Access), for consultants.** hive-author is LAN-only by default. To let consultants promote memory / file corrections from Claude Desktop / claude.ai, front it with its own Cloudflare Access app: a self-hosted app named `hive-author` on hostname `hive-author.example.com` (Managed OAuth on, team `homelab-gateway`, Allow policy scoped to consultant emails), with `cloudflared` routing `hive-author.example.com` direct to `host-a:8016` (bypassing Caddy, like hive-serve). Consultants then add **hive-author** as a second custom Claude connector alongside the read-only hive-serve one - two doors, one read (keyless hive-serve) and one write (`issues:write` hive-author). (CF Access app and cloudflared route are repo-external live infra - verify.)

## Tests

- **Posture.** Fakes-only, no live token or network. The GitHub client is injected: `tests/test_mcp_app.py` builds the app with `build_mcp(Settings(), lambda: FakeIssueClient())`, and `tests/test_github_client.py` exercises `FakeIssueClient` directly. Issue bodies are verified against the **real** hive-gen Issue-Form parsers: `tests/test_submissions.py` dynamically loads `hive-gen/scripts/memory_from_issue.py` and `correction_from_issue.py` and asserts the built body parses back losslessly (client/product/memory/related/citations for memory; corrects/correction/citations for correction), proving round-trip compatibility with the Actions. It also asserts the client-required guard raises `ValueError` and that `submitted_by` lands in the body. `test_mcp_app.py` asserts both tools register and that the memory/correction builders stay hard-separated (disjoint labels and body sections). `vf-hive-gen` is a dev-only dependency (relative source `../hive-gen`, editable) purely so these round-trip tests can import the parsers.
- **How to run.** `cd tooling/hive-author && uv run pytest -q` (per the doc header; the README uses `uv sync --extra dev && uv run pytest -q` to first pull the dev extras).
- **Count.** 11 test functions across 6 files: `test_submissions.py` (4), `test_mcp_app.py` (2), `test_github_client.py` (2), and one each in `test_config.py`, `test_identity.py`, `test_server_http.py`.

# okf-author — write-only OKF authoring MCP server

A small MCP server that files OKF authoring **issues** into GitHub (the 3c memory Action and the
Spec-2 correction Action). It exists so okf-serve stays **keyless / read-only**: okf-author is the
only component holding a GitHub token, and its token needs **`issues:write` only** — it cannot push,
merge, or open PRs (the Actions do that with the built-in `GITHUB_TOKEN`, after a CODEOWNER approve-label).

## Tools (hard-separated)
- `submit_memory_promotion(client, product, title, lesson, …)` — files an `okf-memory` issue. **Requires a client**; never reaches core knowledge.
- `submit_correction(target_concept_id, corrected_fact, rationale, …)` — files an `okf-correction` issue against a core concept. Never client-scoped.

The issue bodies match the `memory.yml` / `correction.yml` Issue Forms exactly, so the Action parsers round-trip them. The submitter is stamped from the CF Access identity header into the issue body.

## Config (env / .env)
- `GITHUB_TOKEN` — fine-grained PAT or GitHub App token, **`issues:write` scope only**, on `example-org/project-hive`.
- `GITHUB_REPO` (default `example-org/project-hive`), `GITHUB_API`, `HOST`, `PORT`, `IDENTITY_HEADER` (default `cf-access-authenticated-user-email`).

## Deploy (operator step)
1. Provision the `issues:write` token → SOPS `infra-repo/secrets/host-a/okf-author.enc.env`.
2. `docker compose -f deploy/compose.yml up -d` on Host-A (binds the LAN IP, its own port).
3. Front it with a CF Access app (own hostname), like okf-serve — the edge sets `Cf-Access-Authenticated-User-Email`.

okf-author is LLM-free and stateless.

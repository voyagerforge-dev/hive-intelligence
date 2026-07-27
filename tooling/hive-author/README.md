# hive-author — write-only OKF authoring MCP server

A small MCP server that files OKF authoring **issues** into GitHub - the Spec-2 correction Action and the
Spec-3 memory Action. It exists so **hive-serve stays keyless / read-only**: hive-author is the only
component that holds a GitHub token, and that token needs **`issues:write` only** — it cannot push,
merge, or open PRs (the Actions do that with the built-in `GITHUB_TOKEN`, and only *after* a CODEOWNER
applies the approve-label). It is LLM-free and stateless.

For the model behind this, see
[Architecture & Concepts: The memory layer](../../docs/OKF-Pipeline.md#the-memory-layer). To use the
tools, see [Guide: Remember and promote a memory](../../docs/runbooks/okf-remember-and-promote.md) and
[Guide: Correct a concept card](../../docs/runbooks/okf-correct-a-card.md).

## Tools (hard-separated)

The two tools **structurally cannot cross** - distinct required params, labels, and destinations:

- `submit_memory_promotion(client, product, title, lesson, context?, platform?, related?, citations?)`
  — files an **`okf-memory`** issue. **Requires a `client`**; can never reach core knowledge.
- `submit_correction(target_concept_id, corrected_fact, rationale, citations?, supersedes?)`
  — files an **`okf-correction`** issue against a core concept. Never client-scoped.

The issue bodies match the `memory.yml` / `correction.yml` Issue Forms exactly, so the same Action
parsers accept them. The submitter is read from the CF Access identity header and stamped into the issue
body (`_Submitted via hive-author by <email>_`).

## Config

Read from the environment (via `env_file` in the compose). The only secret is the token.

| Var | Default | Notes |
|---|---|---|
| `GITHUB_TOKEN` | — | Fine-grained PAT (or GitHub App token), **`issues:write` only**, on `example-org/project-hive`. The only secret. |
| `GITHUB_REPO` | `example-org/project-hive` | Target repo for issues. |
| `GITHUB_API` | `https://api.github.com` | |
| `HOST` / `PORT` | `0.0.0.0` / `8016` | |
| `IDENTITY_HEADER` | `Cf-Access-Authenticated-User-Email` | The trusted header the edge injects; the caller's email → `submitted_by`. |

## Live deployment (Host-A)

- **Container** `hive-author`, bound to **`hive-host.internal:8016`** (VLAN60 LAN, same host model as hive-serve).
- **Image** built from this package via `deploy/Dockerfile` (the build context is the package dir).
- **Secret** decrypted from SOPS to **`/srv/hive-author/hive-author.env`** (mode 600, *outside* the git
  checkout) — never committed.
- **Compose project** is pinned to **`hive-author`** (`name: hive-author` in `deploy/compose.yml`).
  > ⚠️ **Gotcha:** both hive-serve and hive-author deploy dirs are named `deploy`, so without an explicit
  > `name:` they collide on Compose's default project name — and a `docker compose down --remove-orphans`
  > in one dir would remove the other's containers. The explicit `name:` isolates them.

### Deploy / redeploy (operator)

The deploy runs from the Windmill-pulled checkout on Host-A
(`/srv/hive-serve/repo/knowledge/okf/tooling/hive-author/deploy`):

```bash
# 1. Provision the token → SOPS (one-time; rotate before the PAT expires)
sops infra-repo/secrets/host-a/hive-author.enc.env      # GITHUB_TOKEN=github_pat_...

# 2. Decrypt → place on Host-A, outside the checkout (piped, never printed)
sops -d infra-repo/secrets/host-a/hive-author.enc.env \
  | ssh host-a 'sudo mkdir -p /srv/hive-author && sudo tee /srv/hive-author/hive-author.env >/dev/null \
                && sudo chmod 600 /srv/hive-author/hive-author.env'

# 3. Build + start (ensure the checkout is current first: wmill script run f/example/okf/cards_sync)
ssh host-a 'cd /srv/hive-serve/repo/knowledge/okf/tooling/hive-author/deploy \
            && sudo docker compose build && sudo docker compose up -d'

# 4. Validate: healthz + file one real issue from Claude Code, then close it
curl -s hive-host.internal:8016/healthz     # {"ok":true}
```

If a stale `hive-author` container exists under the wrong project (the `deploy` collision), remove it by
name first — this leaves hive-serve untouched: `ssh host-a 'sudo docker rm -f hive-author'` then re-`up`.

## Public edge (CF Access) — for consultants

hive-author is LAN-only by default (reachable from Claude Code on the LAN). To let **consultants** submit
corrections / promote memory from **Claude Desktop / claude.ai**, front it with a Cloudflare Access app,
exactly like hive-serve (see `infra-repo/docs/runbooks/okf-mcp-cf-access-oauth.md`):

1. **CF Access app** (owner: Yash) — Zero Trust → Access → Applications → Add → Self-hosted. Name
   `hive-author`, hostname **`hive-author.example.com`** (no path), **Managed OAuth on**, team
   `homelab-gateway`, policy Allow → the consultant emails. Copy the AUD.
2. **cloudflared** (owner: operator) — route `hive-author.example.com` **direct to `host-a:8016`**
   (bypass Caddy, like hive-serve), reload, validate the `/mcp` OAuth gate.
3. Consultants add **hive-author** as a second custom connector (alongside the read-only hive-serve one).

## Package layout

`hiveauthor/config.py` · `identity.py` · `submissions.py` (issue-body builders + hard-separated `build_*`) ·
`github_client.py` (injectable `issues:write` client; faked in tests) · `mcp_app.py` (the two tools) ·
`server.py`. Tests are fakes-only (`uv sync --extra dev && uv run pytest -q`; the round-trip tests load the
real `hive-gen` parsers to prove the issue bodies parse back losslessly).

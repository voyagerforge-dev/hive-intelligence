# hive-author — write-only OKF authoring MCP server

A small MCP server that files OKF authoring **issues** into GitHub - the Spec-2 correction Action and the
Spec-3 memory Action. It exists so **hive-serve stays keyless / read-only**: hive-author is the only
component that holds a GitHub token, and that token needs **`issues:write` only** — it cannot push,
merge, or open PRs (the Actions do that with the built-in `GITHUB_TOKEN`, and only *after* a CODEOWNER
applies the approve-label). It is LLM-free and stateless.

For the model behind this, see
[Architecture & Concepts: The memory layer](../../docs/architecture/pipeline.md#the-memory-layer). To use the
tools, see the operator runbooks kept with your deployment.

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

## Deployment

Deployment is not described here. hive-author is packaged by `deploy/Dockerfile` and configured by
the keys above; how it is built, where its secret comes from, what address it binds and what
authenticates its callers all belong to whoever runs it. See
`docs/architecture/product-deployment-boundary.md`.

`deploy/compose.example.yml` is a starting point. Two things in it are not decoration:

- The explicit compose `name:`. Both hive-serve and hive-author use a directory called `deploy`, so
  without it they collide on the default project name, and `down --remove-orphans` in one removes the
  other's containers. If a stale container lands under the wrong project, remove it by name
  (`docker rm -f hive-author`) rather than tearing the project down.
- The loopback default on `ports`. hive-author trusts the header named by `IDENTITY_HEADER` and does
  not authenticate callers itself, so exposing it without an authenticating proxy in front hands
  anyone who can reach the port the ability to submit cards as any identity they choose.

## Package layout

`hiveauthor/config.py` · `identity.py` · `submissions.py` (issue-body builders + hard-separated `build_*`) ·
`github_client.py` (injectable `issues:write` client; faked in tests) · `mcp_app.py` (the two tools) ·
`server.py`. Tests are fakes-only (`uv sync --extra dev && uv run pytest -q`; the round-trip tests load the
real `hive-gen` parsers to prove the issue bodies parse back losslessly).

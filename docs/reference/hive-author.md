# hive-author

The write door. Package `hiveauthor`, CLI `hiveauthor`.

The only component that holds a credential, and that credential can open issues and nothing else.
It cannot push, merge, or open a pull request.

Narrative version: [corrections and memory](../guides/corrections-and-memory.md).

## Running

```bash
pip install vf-hive-author==<engine version>
hiveauthor
```

A deployment installs it from the index at the same version as the rest of the engine, the way it
installs `hive-serve`, and runs the console script; the container image under
`tooling/hive-author/deploy/` does the same thing with the same package. It joined the released
set at 0.7.0 - before that a deployment built it from a checkout of this repository, which is the
git pin [distributing the engine](../architecture/engine-distribution.md) exists to retire, left
standing in the one place the fix had not reached.

It serves on `HOST:PORT` (default `127.0.0.1:8000`), exposes `/healthz` and `/metrics`, and mounts
the MCP door at `/`. It **refuses to start** unless the forge settings below are complete, because
an unset `FORGE_REPO` builds `/repos//issues` and 404s every submission while reporting success.

## Why it is a separate service

`hive-serve` is the component exposed to the widest audience, so it holds nothing worth stealing
and can write nothing. Concentrating the write path here is what lets the read path stay keyless.

The consequence is worth stating plainly: **there is no path by which an agent, or anyone using
one, writes a card directly into the corpus.** Every card was merged by a person.

## Two tools

| Tool | Files | Labelled |
|---|---|---|
| `submit_memory_promotion` | a client-scoped memory card | `hive-memory` |
| `submit_correction` | a correction against a concept id | `hive-correction` |

They are hard-separated: separate builders, separate labels, separate validation. Memory promotion
requires a client and refuses without one, because a memory card with no client is either a concept
card or a mistake, and both deserve rejection rather than a guess.

## The round trip

Issue bodies use a `### <section>` layout that mirrors the corpus repository's issue forms exactly,
so the same `hive-gen` parsers read a body whether it came from this service or from someone
filling in the form by hand. One parser, one format, no drift.

From there an automation opens a pull request, but only after a code owner applies the approval
label. The corpus changes when a person merges.

## Modules

| Module | Purpose |
|---|---|
| `submissions.py` | pure issue-body builders, and the client-required guard on memory promotion |
| `issue_client.py` | injectable issue client: a protocol, one client per forge kind, and an in-memory fake for tests |
| `mcp_app.py` | registers the two tools, resolves the caller, delegates to `submissions` |
| `identity.py` | resolve the owner id from the trusted header, else the default |
| `metrics.py` | Prometheus registry and per-tool instrumentation |
| `config.py` | typed settings |
| `server.py` | wire settings and a client factory, mount under a FastAPI app with `/healthz`, run |

`submissions.py` is pure and side-effect free, which is what makes the round-trip guarantee
testable without a network.

## Internals

Module-level detail, verified against the code on 2026-07-30.

### `submissions.py`

**Pure builders, no I/O.** They turn arguments into `{title, body, labels}`.

The body emits `### <label>` sections that match the corpus repository's issue forms **exactly**,
so the same workflow parsers accept an issue whichever way it was filed. That symmetry is the whole
design: one parser, two front doors.

The two builders are hard-separated and cannot cross. Memory **requires** a client and labels
`hive-memory`; correction targets a concept id and labels `hive-correction`.

> Those labels must stay in step with `.github/ISSUE_TEMPLATE/*.yml` in the corpus repository. They
> said `okf-*` here until 2026-07-30 while the forms said `hive-*`, so an issue filed through this
> service carried a different label from the same issue filed through the form, and any label-based
> filter or CODEOWNER route saw only half the submissions. Nothing failed; the halves were just
> invisible to each other.

### `issue_client.py`

A protocol with three implementations: one real client per forge kind, and a fake used throughout
the tests. A real one needs **only** the permission to open issues on one repository.

Injecting the client is what lets the entire suite run with no token and no network, which matters
for a service whose only job is to hold a credential.

**Two clients exist because of one field.** GitHub's issue API takes label *names*; Forgejo's takes
integer *IDs* and answers a name with 422. `FORGE_KIND` selects between them and is refused at
startup if it is unknown, rather than being inferred from `FORGE_API`: guessing wrong fails at the
moment somebody is waiting on a submission. Everything else about the two APIs is close enough to
share.

### `mcp_app.py`, `identity.py`, `server.py`

`mcp_app` exposes exactly two tools, mirroring the two builders. `identity` resolves the submitter
from the trusted gate header so `submitted_by` provenance is server-derived, never a parameter.
`server` is the entrypoint.

## Tests

Fakes only, no network, no token. Use `uv run pytest --collect-only -q` in
`tooling/hive-author/` for the current inventory rather than a count written down here.

## Configuration

See [configuration](configuration.md#hive-author).

`FORGE_API`, `FORGE_REPO` and `FORGE_KIND` have **no default** and are validated at startup,
along with a credential, which is either `FORGE_TOKEN` or `FORGE_TOKEN_FILE`. A plausible-looking
default repository would file issues into somebody else's project, which is worse than failing to
start.

**`FORGE_TOKEN_FILE` exists because some tokens expire faster than the process lives.** A GitHub
App installation token lasts an hour while this server runs for days, so it cannot be an
environment variable read once at startup. Point `FORGE_TOKEN_FILE` at a file that something else
keeps fresh and the client re-reads it on every submission. Set one or the other, never both.

Scope the credential to issue creation on the corpus repository. Anything else it can do is blast
radius.

## Gotchas

**Same identity model as `hive-serve`.** The header is trusted, not verified. Without an
authenticating proxy in front, anyone who can reach the port can file submissions as anyone.

**Compose project name.** Both services use a directory called `deploy`, so without an explicit
compose `name:` they collide on the default project name, and `down --remove-orphans` in one
removes the other's containers. The example compose file sets it. If a stale container lands under
the wrong project, remove it by name rather than tearing the project down.

# hive-author

The write door. Package `hiveauthor`, CLI `hiveauthor`.

The only component that holds a credential, and that credential can open issues and nothing else.
It cannot push, merge, or open a pull request.

Narrative version: [corrections and memory](../guides/corrections-and-memory.md).

## Why it is a separate service

`hive-serve` is the component exposed to the widest audience, so it holds nothing worth stealing
and can write nothing. Concentrating the write path here is what lets the read path stay keyless.

The consequence is worth stating plainly: **there is no path by which an agent, or anyone using
one, writes a card directly into the corpus.** Every card was merged by a person.

## Two tools

| Tool | Files | Labelled |
|---|---|---|
| `submit_memory_promotion` | a client-scoped memory card | `okf-memory` |
| `submit_correction` | a correction against a concept id | `okf-correction` |

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
| `github_client.py` | injectable issue client: a protocol, a real client, and an in-memory fake for tests |
| `mcp_app.py` | registers the two tools, resolves the caller, delegates to `submissions` |
| `identity.py` | resolve the owner id from the trusted header, else the default |
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

### `github_client.py`

A protocol with two implementations: the real HTTP client, and a fake used throughout the tests. The
real one needs **only `issues:write`**.

Injecting the client is what lets the entire suite run with no token and no network, which matters
for a service whose only job is to hold a credential.

### `mcp_app.py`, `identity.py`, `server.py`

`mcp_app` exposes exactly two tools, mirroring the two builders. `identity` resolves the submitter
from the trusted gate header so `submitted_by` provenance is server-derived, never a parameter.
`server` is the entrypoint.

## Tests

11 tests. Fakes only, no network, no token.

## Configuration

See [configuration](configuration.md#hive-author).

`GITHUB_TOKEN` and `GITHUB_REPO` have **no default** and are validated at startup. A
plausible-looking default repository would file issues into somebody else's project, which is worse
than failing to start.

Scope the token to issue creation on the corpus repository. Anything else it can do is blast radius.

## Gotchas

**Same identity model as `hive-serve`.** The header is trusted, not verified. Without an
authenticating proxy in front, anyone who can reach the port can file submissions as anyone.

**Compose project name.** Both services use a directory called `deploy`, so without an explicit
compose `name:` they collide on the default project name, and `down --remove-orphans` in one
removes the other's containers. The example compose file sets it. If a stale container lands under
the wrong project, remove it by name rather than tearing the project down.

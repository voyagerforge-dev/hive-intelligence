# hive-serve

The runtime that hands cards to an agent. Package `hiveserve`, CLI `hiveserve`.

One core, two doors, two stores. The serving path calls no model: retrieval is id lookup plus
cross-link traversal, and search is token matching.

Narrative version: [serving cards](../guides/serving-cards.md).

## Running

```bash
hiveserve serve --http      # REST and MCP over HTTP
hiveserve serve --stdio     # MCP over stdio, for Claude Desktop and Claude Code
```

## REST

| Route | Returns |
|---|---|
| `GET /healthz` | `{"ok":true}` if the process is alive. **Not a corpus check** |
| `GET /metrics` | Prometheus exposition |
| `GET /concepts` | lean index: id, title, product, type |
| `GET /find_concepts?q=` | token search over titles and descriptions |
| `GET /card/{card_id}` | one card as raw markdown |
| `POST /resolve` | a bundle: cards, their links, their corrections |

`POST /resolve` takes `{"ids": [...], "depth": 1}` and **rejects unknown fields**. `client` in
particular is not accepted: the REST door serves shared knowledge only, and silently ignoring the
field would return a 200 that looks exactly like scoping working.

## MCP tools

Fifteen, in three groups.

**Retrieval:** `list_concepts`, `find_concepts`, `get_card`, `resolve`, `find_db_objects`

**Work ledger:** `start_objective`, `list_objectives`, `get_objective`, `append_entry`,
`set_status`, `record_quiz_result`

**Personal memory:** `remember`, `recall`, `forget`, `promote`

`promote` does not write to the corpus. It proposes, through `hive-author`.

## Modules

| Module | Purpose |
|---|---|
| `resolver.py` | the core: id to file mapping, corpus index, cross-link traversal with isolation guards, corrections co-pull |
| `tools.py` | transport-agnostic wrappers over the resolver, shared by both doors |
| `dbobjects.py` | keyword search over the per-product database-object manifests; backs `find_db_objects` |
| `ledger.py` | SQLite objectives, entries and personal memory, with enum validation and owner-scoped access |
| `identity.py` | resolve the caller's owner id from the trusted header, else the configured default |
| `app.py` | the REST door |
| `mcp_app.py` | the MCP door, each tool metrics-wrapped |
| `server.py` | CLI and ASGI assembly |
| `config.py` | typed settings |
| `metrics.py` | Prometheus registry, instrumentation, TTL-cached corpus gauges |
| `index.py` | emit `index.md` and render `related` into inline links. Not on the serving path |
| `agent.py`, `eval.py`, `run_eval.py` | offline evaluation. **Not on the serving path** |

`tools.py` existing is the reason the two doors cannot drift: both call the same wrappers, and
isolation is enforced once.

## The resolver

**Ids are paths.** `widget/calibration-routine` maps to `<concepts>/widget/calibration-routine.md`;
ids beginning `clients/` map under `<clients>`. A path that escapes its base resolves to `None`, so
a traversal attempt returns a missing card rather than a file.

**Client scope is structural**, derived from the id path rather than a frontmatter field. A card is
in scope when its client matches the caller's, or when it has no client. A frontmatter field can be
absent or wrong; a path cannot.

**The index excludes the database-object tier.** `concepts/<product>/db/**` is skipped, because a
real schema would swamp it. Those cards are reached through `find_db_objects` and by id.

**Corrections attach automatically**, but only with `status: approved`. A draft correction is inert.

## The ledger

One SQLite file at `OKF_DATA_DIR`, holding objectives, their entries and personal memory, keyed by
owner and validated against enums.

**The only state in the system that is not in git.** Cards restore from any clone. This does not.

## Identity

`IDENTITY_HEADER` names a header that is **trusted on arrival and never verified**. Whatever it
contains becomes the owner and the client scope.

Anything that can reach the port can claim any identity. The default binding is loopback for that
reason, and an authenticating proxy that strips the header from inbound requests is required, not
advisable, for any exposure beyond the host.

## Metrics

See [metrics](metrics.md). The short version: `/healthz` cannot see an empty corpus, so alert on
`okf_corpus_cards` and `okf_corpus_db_objects`. Both, because the first excludes the
database-object tier and that tier is usually most of the corpus.

## The evaluation harness

`agent.py`, `eval.py` and `run_eval.py` score retrieval against labelled question sets. They **do**
call a model, through `hivegen`, and are never on the serving path.

Question sets name real card ids, so they are corpus-specific and ship with a corpus rather than
with the product. `run_eval` therefore requires the set as an argument and has no default.

## Configuration

See [configuration](configuration.md#hive-serve).

## Gotchas

**`/healthz` reports healthy on an empty corpus.** This has caused a real outage.

**Bind mounts resolve at container start.** If a corpus directory is deleted and recreated beneath a
running container, it keeps the old inode and keeps serving the detached contents. Re-seeding a
corpus needs a restart; editing files inside it does not.

**Cards are read live.** A card edited in the corpus is served on the next request. Code changes
need a rebuild; content changes do not.

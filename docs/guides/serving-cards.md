# Serving cards

`hive-serve` is one core with two doors. It makes no model calls, holds no credentials, and does
not authenticate callers.

That last point is the one to read twice.

## Running it

```bash
CONCEPTS_DIR=/path/to/corpus/concepts \
CLIENTS_DIR=/path/to/corpus/clients \
OKF_DATA_DIR=/path/to/ledger \
uv run hiveserve serve --http     # or --stdio for MCP
```

`--http` serves REST and MCP over HTTP. `--stdio` is the transport Claude Desktop and Claude Code
speak directly. Full settings in [configuration](../reference/configuration.md).

## Identity, and what it is not

`hive-serve` trusts a header. It does not verify one.

`IDENTITY_HEADER` names the header carrying the caller's identity, and whatever arrives in it
becomes the owner for ledger operations and the client scope for isolation. There is no signature
check, no token validation, and no session.

**This means anything that can reach the port can claim to be anyone.** The binding in the example
compose file defaults to loopback for exactly this reason. In any deployment reachable beyond the
host, an authenticating proxy in front is not a hardening step, it is the only thing standing
between a caller and another client's memory cards.

The design is deliberate: authentication belongs to whatever your organisation already uses, and a
service that implements its own is a service with its own auth bugs. But it is only safe if the
proxy is actually there and actually strips the header from inbound requests.

## The REST door

| Route | Returns |
|---|---|
| `GET /healthz` | `{"ok":true}` if the process is alive |
| `GET /metrics` | Prometheus exposition |
| `GET /concepts` | lean index: id, title, product, type |
| `GET /find_concepts?q=` | ranked keyword search over ids, titles and descriptions |
| `GET /card/{card_id}` | one card, raw markdown |
| `POST /resolve` | a bundle: several cards plus their corrections |

### `/healthz` is not a corpus check

It reports that the process is running. A service whose corpus mount has gone stale or empty
returns `{"ok":true}` and serves nothing.

This is not hypothetical. It has cost one outage of about two hours, during which health checks
were green throughout. Alert on the card-count gauge, never on health. See
[metrics](../reference/metrics.md).

### REST serves shared knowledge only

Client-scoped memory and issue cards are **not reachable over REST**. That door has no identity
plumbing, so it serves only what is shared.

Asking for client scoping is rejected rather than ignored:

```bash
curl -X POST localhost:8015/resolve -d '{"ids":["x"],"client":"alpha"}'
# 422
```

A silent ignore would return 200 with a shared-only answer, and the caller would have no way to
know the scoping was never applied. That failure mode looks exactly like isolation working.

### `/resolve` is the interesting one

Given ids, it returns a bundle: the cards, the cards they link to up to `depth`, and any approved
corrections that target any of them. Bounded by `MAX_CARDS` and `MAX_CHARS` so a bundle cannot grow
without limit.

Corrections arrive whether or not they were asked for. An agent reading a bundle cannot see a
superseded claim without also seeing the amendment.

## The MCP door

Fifteen tools in three groups.

**Retrieval**

| Tool | Does |
|---|---|
| `list_concepts` | the lean index, optionally filtered by product or client |
| `find_concepts` | ranked keyword search |
| `get_card` | one card by id |
| `resolve` | a bundle, with corrections attached |
| `find_db_objects` | search the database-object tier, which is excluded from the index |

**Work ledger**

| Tool | Does |
|---|---|
| `start_objective` | begin a piece of work in a mode |
| `list_objectives` | this owner's objectives |
| `get_objective` | one objective with its entries |
| `append_entry` | add a finding, note or decision |
| `set_status` | move an objective on |
| `record_quiz_result` | record a self-check against a concept |

**Personal memory**

| Tool | Does |
|---|---|
| `remember` | store a private note |
| `recall` | retrieve private notes |
| `forget` | delete one |
| `promote` | propose a private note become shared knowledge |

`promote` does not write to the corpus. It files a submission for review; see
[corrections and memory](corrections-and-memory.md).

## Client isolation

Cards under `clients/<client>/` are scoped to that client, derived structurally from the id path
rather than from a frontmatter field. A card is in scope only when its client matches the caller's,
and cards with no client are shared.

Enforcement lives in the resolver, so both doors get it from the same place and neither can drift.

**What this does and does not give you.** It is a serving-time control. Every client's cards sit in
one repository, separated by directory. Anyone who can read the repository can read all of them.
If clients need separation stronger than that, they need separate corpora.

## The ledger

One SQLite file at `OKF_DATA_DIR`, holding objectives, their entries, and personal memory, keyed by
owner.

**It is the only state in the system that is not in git.** Cards can be restored from any clone.
The ledger cannot be restored from anywhere unless you have backed it up. If you take one
operational action after reading this page, make it that one.

## Corpus freshness

Cards are read live from disk. A card edited in the corpus is served on the next request with no
restart and no rebuild.

Code changes need a rebuild. Corpus changes do not.

One exception worth knowing, because it is a foot-gun: if the corpus directory is a **bind mount**
and the host directory is deleted and recreated, the container keeps the old inode and keeps
serving the old, now-detached contents. Re-seeding a corpus in place requires a restart. Editing
files within it does not.

# Serving cards

`hive-serve` is one core with two doors. It makes no model calls, holds no credentials, and does
not authenticate callers.

That last point is the one to read twice.

## Running it

```bash
CONCEPTS_DIR=/path/to/corpus/concepts \
CLIENTS_DIR=/path/to/corpus/clients \
LEDGER_DSN=postgresql://user:password@host:5432/hive_ledger \
uv run hiveserve serve --http     # or --stdio for MCP
```

`--http` serves REST and MCP over HTTP. `--stdio` is MCP over stdio, which is what most desktop
and editor agents speak directly. Neither starts without `LEDGER_DSN`.

`CLIENTS_DIR` is optional: leave it empty to disable client memory entirely. `CONCEPTS_DIR` is
required and has no default - see
[configuration](../reference/configuration.md#concepts_dir-has-no-default) for why it
lost the one it had, and [the table](../reference/configuration.md#hive-serve) for the full set.

## Identity, and what it is not

`hive-serve` trusts a header. It does not verify one.

`IDENTITY_HEADER` names the header carrying the caller's identity, and whatever arrives in it
becomes the owner for ledger operations. It does not select or authorize a retrieval client. There
is no signature check, no token validation, and no session.

Hive serves **one trusted organization**. Authenticated personnel may select any client as retrieval
context; there is no per-client authorization or cross-organization tenancy. Operators must keep
confidential client information out of shared knowledge. That operating expectation is not evidence
that an existing corpus contains no confidential material; private corpora and raw evaluation
reports must still be handled privately.

**This means anything that can reach the port can claim to be anyone.** The binding in the example
compose file defaults to loopback for exactly this reason. In any deployment reachable beyond the
host, an authenticating proxy is required to restrict access to organization personnel and establish
ledger ownership. It does not restrict which client's knowledge an authenticated operator can read.

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

Use MCP for client context. See [the REST contract](../reference/hive-serve.md#rest) for its
shared-only surface and how unsupported client parameters are handled.

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

## Client context

Select the client whose system the question concerns, so its modifications and incidents do not
become another site's guidance. See [the resolver's scope rules](../reference/hive-serve.md#the-resolver)
and [search candidates](../reference/hive-serve.md#search) for the per-tool contract.

As explained in [the trust boundary](#identity-and-what-it-is-not), this is retrieval context, not
access control. Anyone who can read the corpus repository can also read all of it. Deployments
requiring an independent trust boundary need separate corpora and separately controlled access.

## The ledger

Postgres, at `LEDGER_DSN`, holding objectives, their entries, and personal memory, keyed by owner.
The [hive-serve reference](../reference/hive-serve.md#the-ledger) has the storage contract; this
page will not repeat it.

**It is the only state in the system that is not in git.** Cards can be restored from any clone.
The ledger cannot be restored from anywhere unless you have backed it up. If you take one
operational action after reading this page, make it that one - and note that being a database
someone's platform will back up is precisely why it stopped being a file.

## Corpus freshness

Cards are read live from disk. A card edited in the corpus is served on the next request with no
restart and no rebuild.

Code changes need a rebuild. Corpus changes do not.

One exception worth knowing, because it is a foot-gun: if the corpus directory is a **bind mount**
and the host directory is deleted and recreated, the container keeps the old inode and keeps
serving the old, now-detached contents. Re-seeding a corpus in place requires a restart. Editing
files within it does not.

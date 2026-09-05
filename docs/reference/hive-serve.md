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
| `GET /find_concepts?q=` | ranked keyword search over card ids, titles and descriptions |
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
| `ranking.py` | the keyword scorer behind `find_concepts` |
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

## Search

`find_concepts` ranks concept cards with `ranking.py`. It is deliberately small - no embeddings,
no network, no runtime dependency past the standard library, and no state that outlives the call.

**`find_db_objects` is not on this scorer and its ranking is unchanged:** it still counts
case-insensitive substring hits, because matching a fragment of a half-remembered schema object name
(`alloc` finding `ALLOCATION`) is what that door is for, and whole-token matching would remove it.
Bringing it onto `ranking.py` needs prefix or stem matching first, and is tracked as follow-up.

**Query and card text are tokenised the same way:** lowercased, then split on runs of letters and
digits. Punctuation therefore never sticks to a token, so the `12` in "…in release 12?" is a term
rather than the unmatchable `12?`. A card id contributes its slug words on exactly these terms, so
`widget/calibration-priority-rules` is searchable as four words, weighed like title words.

**A small fixed list of English function words is dropped** from both sides. A query made only of
them matches nothing, which is the honest answer; previously it returned the whole corpus in
alphabetical order.

**Matching is whole-token,** not substring: `at` no longer matches inside "catalogue".

**Ranking is inverse document frequency with sublinear term frequency.** A term that occurs in few
cards is worth more than one that occurs in most, and a card that uses the term repeatedly outranks
one that mentions it once without repetition dominating. Document frequencies are computed on each
call from the candidate cards that call is ranking - the ones left after the `type` and `product`
filters - so a scoped search weights terms against its own subset. Ties break by id, so the order is
deterministic.

**What it still does not read:** card bodies, and the `regime` / `version` frontmatter facets. A
question that names a regime or a release is naming something the corpus knows and this search
cannot use.

Measured on a ~990-card corpus against 70 labelled questions at the default `limit=20`, this scorer
places the expected card in the returned set for 92.9% of them, against 77.1% for the token-counting
scorer it replaced, with no question ranked worse than before. The gap between the two also widens
with corpus size, which is what made the old scorer feel like it got worse as a corpus grew.

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
`hive_corpus_cards` and `hive_corpus_db_objects`. Both, because the first excludes the
database-object tier and that tier is usually most of the corpus.

## The evaluation harness

`agent.py`, `eval.py` and `run_eval.py` score retrieval against labelled question sets. They **do**
call a model, through `hivegen`, and are never on the serving path.

Question sets name real card ids, so they are corpus-specific and ship with a corpus rather than
with the product. `run_eval` therefore requires the set as an argument and has no default. A bare
name resolves under `EVAL_DIR`; a path with a suffix is taken as given. The cards come from
`CONCEPTS_DIR`.

Both are checked before any model is called. An absent or empty corpus scores zero on every question
and reports an aggregate as though it had measured something, so `run_eval` refuses instead, naming
the setting. "Empty" is `load_index`'s definition, not "holds no `.md`", since `index.md`, `log.md`
and the `<product>/db/` tier are not cards. `CLIENTS_DIR` stays optional: `run_eval` refuses only
when the set it was handed has rows expecting client cards, and otherwise - when the setting was
actually configured, rather than left at its default - prints that a dead path disabled client
memory rather than degrading quietly. When it is set, existing is not
enough either - `run_eval` asks `load_index` which clients it can serve and refuses naming the ones
it cannot. What counts as "needed" is which clients a row expects **cards** for - an `expects_memory`
id, or a `clients/<client>/...` entry in `expected_card_ids` - never the `client` field alone. A
control client in an isolation set deliberately has no memory of its own, and demanding cards for it
would refuse the deploy gate. Such a run is allowed to proceed but not to be read as cross-client
isolation: `score_memory` counts a card only when its client differs from the row's, so when no row
has any served client out of its own scope, `cross_client` scores zero because nothing could have
leaked rather than because isolation held. `run_eval` says so on stdout **and** records
`cross_client_unexercised` beside the aggregate, because the report is what outlives the terminal.
That flag is scoped to `cross_client` alone: `memory_ok` for a row carrying `expects_memory` stays a
real and failable measurement, since it also requires that client's own memory card to have been
retrieved. Reports are written under `OKF_DATA_DIR`.

## Internals

Module-level detail, verified against the code on 2026-07-30.

### `resolver.py`, the whole retrieval algorithm

Everything selection-related lives here, which is why both doors cannot drift apart on isolation.

**`card_path`** maps a card id to a file. Ids starting `clients/` resolve under `CLIENTS_DIR`,
everything else under `CONCEPTS_DIR`. Both are resolved and bounds-checked, so a crafted id cannot
escape its directory.

**`clients_base`** is where "empty means client memory is off" is decided, once, for every caller.
`Path("")` is `Path(".")` and exists, so an empty `CLIENTS_DIR` that reached `card_path` or
`load_index` directly would have scanned the working directory and answered `clients/…` ids out of
it. Both doors, the metrics collector and the eval all funnel through here, so none of them can
disagree about what "unset" means.

**`load_index`** builds the lean index. It reads frontmatter only, never bodies. Client cards get a
`client` facet **derived from the id path**, not from author-supplied frontmatter, so a card cannot
declare itself into another client's scope.

**`resolve`** is a breadth-first walk with three independent limits and two guards:

```
seed        ids that exist AND are in scope
expand      follow related: edges, up to `depth` levels
budget      stop at `max_cards` (default 8); then optionally trim to `max_chars`
```

The two guards run on every neighbour, and both share a subtlety worth stating:

| Guard | Rule |
|---|---|
| Cross-regime | skip a neighbour whose regime differs from its parent's |
| Cross-client | skip a neighbour scoped to a different client than the active one |

> **A skipped neighbour is deliberately not marked as seen.** It stays reachable by another path
> that legitimately leads to it. Marking it seen would let the first, rejected traversal
> permanently hide a card from a valid one, and the symptom would be an answer missing a card for
> reasons invisible in the output.

**Broken links are tolerated.** A `related:` id with no file is skipped silently rather than
raising. A corpus mid-edit stays servable; `validate-atomic` and the lint scripts are where dangling
links are supposed to be caught.

**The character budget always keeps at least one card.** The trim only drops a card if something is
already kept, so a single card larger than `max_chars` is returned rather than an empty bundle.

**Corrections are co-pulled last and are unbudgeted.** After selection and trimming, every active
correction of every selected concept is appended. They are not subject to `max_cards` or
`max_chars`, because a dropped correction means the wrong fact stands.

The return is `{card_ids, bundle, dropped, corrections}`. `dropped` is what the budget removed, and
it is worth surfacing: a silently truncated bundle looks like a complete answer.

### `dbobjects.py`

LLM-free keyword search over `concepts/<product>/db/manifest.jsonl`, one JSON object per line,
emitted by the parser. Case-insensitive token matching, **scored by how many query tokens hit**,
optionally filtered by kind or module, capped by `limit` (default 20).

The same shape as memory `recall`, deliberately. Neither calls a model, so both are cheap enough to
sit in a tool loop and deterministic enough to test. This door keeps substring matching on purpose;
see [Search](#search) for why `find_concepts` moved off it and this one has not.

### `ledger.py`

Three tables in one SQLite file, WAL mode: `objective`, `entry`, `memory`. Enum-validated on write
and **owner-scoped on every read and write**.

### `identity.py`

Resolves `owner` from the configured trusted header, falling back to the configured default when
there is no header (stdio, where there is no gate in front).

Header lookup is **case-insensitive**: it tries the exact name, then retries against a lowercased
view of the keys, because a plain dict is case-sensitive while HTTP headers are not. A gate that
sends a differently-cased header would otherwise silently produce the default owner for everyone,
which is a data-mixing bug rather than an error.

### `app.py`, `mcp_app.py`, `server.py`

`app.py` is the FastAPI REST router. `mcp_app.py` is the FastMCP server: 15 tools, no prompts,
injecting `owner` from the request context so it can never be a tool parameter. `server.py` is the
entrypoint that mounts the MCP streamable-HTTP app onto the same FastAPI process for `--http`, or
runs stdio.

### `agent.py`, `eval.py`, `run_eval.py`

The offline evaluation harness. **Not on the serving path** and the only part of this package that
calls a model. It exists to measure the corpus, and the product-isolation eval over it is the
deploy gate.

## Tests

193 tests, 3 of which skip without a live corpus. Fakes only, no network. Assertions that need a live corpus, its evaluation
datasets, or the GitHub
submission surface skip with a stated reason when their subject is absent, so the suite is green in
this repository and meaningful in a deployment that has a corpus.

## Configuration

See [configuration](configuration.md#hive-serve).

## Gotchas

**`/healthz` reports healthy on an empty corpus.** This has caused a real outage.

**Bind mounts resolve at container start.** If a corpus directory is deleted and recreated beneath a
running container, it keeps the old inode and keeps serving the detached contents. Re-seeding a
corpus needs a restart; editing files inside it does not.

**Cards are read live.** A card edited in the corpus is served on the next request. Code changes
need a rebuild; content changes do not.

# hive-serve

The runtime that hands cards to an agent. Package `hiveserve`, CLI `hiveserve`.

One core, two doors, two stores. The serving path calls no model: retrieval is id lookup plus
cross-link traversal, and search is token matching.

Narrative version: [serving cards](../guides/serving-cards.md).

## Running

```bash
hiveserve serve --http      # REST and MCP over streamable HTTP
hiveserve serve --stdio     # MCP over stdio, for any client that speaks it
```

Both transports require `LEDGER_DSN` and refuse to start without it. See
[the ledger](#the-ledger).

## REST

| Route | Returns |
|---|---|
| `GET /healthz` | `{"ok":true}` if the process is alive. **Not a corpus check** |
| `GET /metrics` | Prometheus exposition |
| `GET /concepts` | lean index: id, title, product, type |
| `GET /find_concepts?q=` | ranked keyword search over card ids, titles and descriptions. Shared cards only |
| `GET /card/{card_id}` | one card as raw markdown |
| `POST /resolve` | a bundle: cards, their links, their corrections |

`POST /resolve` takes `{"ids": [...], "depth": 1}` and **rejects unknown fields**. `client` in
particular is not accepted: the REST door serves shared knowledge only, and silently ignoring the
field would return a 200 that looks exactly like scoping working.

`GET /find_concepts` takes no `client` either, and neither does `GET /concepts`; unknown query
parameters are ignored. REST's existing surface is shared-only and does not load the clients tree.
MCP accepts a caller-selected client as retrieval context, independently of ledger identity.

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
| `ledger.py` | Postgres objectives, entries and personal memory, with enum validation and owner-scoped access |
| `identity.py` | resolve the caller's owner id from the trusted header, else the configured default |
| `app.py` | the REST door |
| `mcp_app.py` | the MCP door, each tool metrics-wrapped |
| `server.py` | CLI and ASGI assembly |
| `config.py` | typed settings |
| `metrics.py` | Prometheus registry, instrumentation, TTL-cached corpus gauges |
| `index.py` | emit `index.md` and render `related` into inline links. Not on the serving path |
| `agent.py`, `eval.py`, `run_eval.py` | offline evaluation. **Not on the serving path** |

Both doors call the transport-agnostic wrappers in `tools.py`. REST supplies only the concepts tree;
MCP also supplies the clients tree and, for scoped operations, the caller-selected client.

## The resolver

**Ids are paths.** `widget/calibration-routine` maps to `<concepts>/widget/calibration-routine.md`;
ids beginning `clients/` map under `<clients>`. A path that escapes its base resolves to `None`, so
a traversal attempt returns a missing card rather than a file.

**Client scope is structural**, derived from the id path rather than a frontmatter field. Listings
and the evaluation selector exclude corrections and use `resolver.out_of_client_scope` to exclude
memory and issue cards unless their client matches the selected `client`. Bundle traversal checks
client context directly from ids, admitting shared cards and the selected client's cards. Search's
narrower candidate set is described [below](#search). MCP `get_card` loads any known card id without
a client argument. For the trust boundary, see [Identity](#identity).

**The index excludes the database-object tier.** `concepts/<product>/db/**` is skipped, because a
real schema would swamp it. Those cards are reached through `find_db_objects` and by id.

**Corrections attach automatically**, but only with `status: approved`. A draft correction is inert.

## Search

`find_concepts` ranks concept cards with `ranking.py`. It is deliberately small - no embeddings,
no network, no runtime dependency past the standard library, and no state that outlives the call.

**`find_concepts` takes an optional `client`** (MCP door only, see above). Named, it adds that
client's own `memory` cards to the candidate set, never issue cards; unnamed, the candidates are the
concept tier alone, exactly as before. `product` and `limit` still apply, and each hit retains the
same fields: `id`, `title`, `product`, `description`. Adding memory widens the collection used for
idf, so a client-scoped search can order shared concepts differently from an unscoped search.
Previously, memory could be discovered through a client-scoped listing but not through search.

**`find_db_objects` is not on this scorer and its ranking is unchanged:** it still counts
case-insensitive substring hits, because matching a fragment of a half-remembered schema object name
(`alloc` finding `ALLOCATION`) is what that door is for, and whole-token matching would remove it.
Bringing it onto `ranking.py` needs prefix or stem matching first, and is tracked as follow-up.

**Query and card text are tokenised the same way:** lowercased, then split on runs of letters and
digits *in any script*, with the underscore separating words. Punctuation therefore never sticks to
a token, so the `12` in "…in release 12?" is a term rather than the unmatchable `12?`. A card id
contributes its slug words on exactly these terms, so `widget/calibration-priority-rules` is
searchable as four words, weighed like title words. No word segmentation is performed, so text in a
space-free script such as Japanese or Chinese is tokenised at run level: a run between separators is
one term, matched whole against the same runs in the cards.

**A small fixed list of English function words is dropped** from both sides. A query made only of
them matches nothing, which is the honest answer; previously it returned the whole corpus in
alphabetical order.

**Matching is whole-token,** not substring: `at` no longer matches inside "catalogue".

**Ranking is inverse document frequency with sublinear term frequency.** A term that occurs in few
cards is worth more than one that occurs in most, and a card that uses the term repeatedly outranks
one that mentions it once without repetition dominating. Document frequencies are computed on each
call from the candidate cards that call is ranking - the ones left after the type, product and
client-scope filters - so a scoped search weights terms against its own subset. Ties break by id,
so the order is deterministic.

**What it still does not read:** card bodies, and the `regime` / `version` frontmatter facets. A
question that names a regime or a release is naming something the corpus knows and this search
cannot use.

Measured on a ~990-card corpus against 70 labelled questions at the default `limit=20`, this scorer
places the expected card in the returned set for 92.9% of them, against 77.1% for the token-counting
scorer it replaced, with no question ranked worse than before. The gap between the two also widens
with corpus size, which is what made the old scorer feel like it got worse as a corpus grew.

## The ledger

**Postgres, at `LEDGER_DSN`.** Objectives, their entries and personal memory, keyed by owner and
validated against enums.

`LEDGER_DSN` has no default and there is no file fallback: `hiveserve serve` refuses to start
without it, on either transport. `OKF_DATA_DIR` is unrelated scratch space and despite its name
holds no ledger.

It was a SQLite file under `OKF_DATA_DIR` until 2026-08-19. It moved because it is the only
mutable state this service holds, and a managed platform backs up a database it manages and does
not back up a file in a volume. Being a database is what makes it get backed up. There is
deliberately no dual-engine support: two placeholder styles chosen at runtime is how you get a
query that is fine against the engine you tested and broken against the one you deployed.

**The only state in the system that is not in git.** Cards restore from any clone. This does not.

## Identity

See [the serving trust boundary](../guides/serving-cards.md#identity-and-what-it-is-not) for ledger
identity, caller-selected retrieval context, and the required authenticating proxy.

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

### What the judge is shown, and what `correct` and `grounded` mean

**Scoring contract changed on 2026-09-06. `correct` and `grounded` scores from the old,
expected-only reference are not comparable with scores under this contract; do not combine them
in one comparison table.** Identify the contract by the evaluated engine revision, not merely the
report's creation date.

The judge's REFERENCE is now the **union of the row's `expected_card_ids` and the bundle the
answerer actually saw**, expected cards first, de-duplicated, with no truncation in either progressive
or ceiling mode. Bundle members use the exact card texts delivered to the answerer, even if those
files change or disappear during the model call; only expected-only cards are loaded separately.
Missing expected-only cards are omitted. The union prevents correctly retrieved evidence outside
the labelled expected set from being invisible to the judge.

The grading prompt is unchanged: `correct` and `grounded` are model verdicts against that
REFERENCE. It can include expected-only cards the answerer did not see, so `grounded` is not a
separate proof of support from the delivered bundle alone. The deterministic metric definitions
(`select_hit`, `bundle_hit`, `regime_ok`, `version_ok`, `product_ok`, `correction_ok`, `memory_ok`)
are unchanged; their values can still change when the selector's candidate set changes.

### A model that returns nothing fails the run

`unscored` alone does not distinguish an unparseable judge reply from no reply. Rows therefore
carry `select_empty`, `answer_empty` and `judge_empty`, treating `None`, empty strings and
whitespace-only replies as empty. The aggregate carries their counts plus `failed`, which is true
if any of the three roles returned nothing on **any** row. Such a report is incomplete, not a
valid low-scoring baseline.

After writing the report, the CLI prints one diagnostic per failing role naming its setting,
configured model and affected row count, then **exits with status 1**. Check `BIFROST_API_KEY`,
gateway model availability and provider quota; an exhausted token plan can fail calls even with a
valid key. Model defaults and overrides are in [configuration](configuration.md#hive-serve).

An unparseable-but-present judge reply still scores `unscored` and does **not** by itself fail the
run. The same holds for the selector: a reply this cannot parse, or one naming only unknown ids,
is a genuine retrieval miss measured by `select_hit` and `bundle_hit`.

**`select_empty` joined them on 2026-09-06.** The selector was excluded until then, on the
reasoning that a selector returning nothing is just a retrieval miss. DeepSeek V4 Flash 0731,
measured as a candidate selection default, produced no usable `card_ids` list on 16 of 16 real
selection prompts: 7 empty responses and 9 replies in a different JSON schema. The 7 are what this
guard catches - the harness scored them as retrieval misses and reported a collapse it had never
observed, the same shape of false zero the answer and judge guards already existed to prevent. The
other 9 are not covered and are not meant to be: a wrong-schema reply is an unparseable selection
naming no card ids, which stays a genuine retrieval miss by the rule above.

## Internals

Module-level detail, verified against the code on 2026-07-30.

### `resolver.py`, the whole retrieval algorithm

Index construction and bundle traversal live here. Their client scope is retrieval context, not
an identity-bound access control.

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

The internal return also includes `card_texts`, an id-to-text mapping captured when `bundle` is
assembled. `agent.answer_question` passes it to the evaluator as `bundle_cards` for the judge's
reference. The transport wrapper strips it: REST and MCP still return only
`{card_ids, bundle, dropped, corrections}`. `dropped` is what the budget removed, and it is worth
surfacing: a silently truncated bundle looks like a complete answer.

### `dbobjects.py`

LLM-free keyword search over `concepts/<product>/db/manifest.jsonl`, one JSON object per line,
emitted by the parser. Case-insensitive token matching, **scored by how many query tokens hit**,
optionally filtered by kind or module, capped by `limit` (default 20).

The same shape as memory `recall`, deliberately. Neither calls a model, so both are cheap enough to
sit in a tool loop and deterministic enough to test. This door keeps substring matching on purpose;
see [Search](#search) for why `find_concepts` moved off it and this one has not.

### `ledger.py`

Three tables in one Postgres database: `objective`, `entry`, `memory`. Enum-validated on write and
**owner-scoped on every read and write**. `entry` and `memory` carry a `seq BIGSERIAL` that
replaces SQLite's `rowid` as the tiebreaker for equal timestamps; without it the order of two rows
written in the same clock tick is whatever the planner returns.

The schema is created on first connection, one statement at a time, because psycopg reports a
multi-statement failure against the whole batch rather than the statement.

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

The selector uses the [index scope filter](#the-resolver) before constructing its model prompt,
not merely when resolving the selected ids. This keeps out-of-context issue titles and descriptions
off the gateway as well as out of the answer bundle. See [the harness contract](#the-evaluation-harness)
for reference construction and failure reporting.

## Tests

See [contribution testing guidance](../../CONTRIBUTING.md#getting-set-up) for setup and the
live-corpus and Postgres requirements. Tests live in `tooling/hive-serve/tests/`; use pytest's
`--collect-only -q` there for the current inventory rather than a hand-maintained count.

## Configuration

See [configuration](configuration.md#hive-serve).

## Gotchas

**`/healthz` reports healthy on an empty corpus.** This has caused a real outage.

**Bind mounts resolve at container start.** If a corpus directory is deleted and recreated beneath a
running container, it keeps the old inode and keeps serving the detached contents. Re-seeding a
corpus needs a restart; editing files inside it does not.

**Cards are read live.** A card edited in the corpus is served on the next request. Code changes
need a rebuild; content changes do not.

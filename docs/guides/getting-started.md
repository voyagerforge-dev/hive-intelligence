# Getting started

Serve the bundled fixture corpus and query it. About five minutes, no credentials of your own, no
corpus of your own, no model calls.

Every command and every output below was run against this repository from a clean checkout.

## Prerequisites

Python 3.12 or later, [uv](https://docs.astral.sh/uv/), and **docker or podman**.

The container runtime is for one throwaway Postgres. `hive-serve` keeps its work ledger in
Postgres and refuses to start without one; there is no file fallback, on purpose. See
[the ledger](../reference/hive-serve.md#the-ledger) for why.

## 1. Install

```bash
cd tooling/hive-serve
uv sync --extra dev
```

## 2. Start a throwaway ledger

```bash
podman run -d --rm --name hive-demo-pg \
  -e POSTGRES_USER=hive -e POSTGRES_PASSWORD=hive -e POSTGRES_DB=hive \
  -p 5433:5432 docker.io/library/postgres:16-alpine
```

`docker` works identically. The credentials are throwaway and the container is deleted when you
stop it; nothing here is a pattern for a real deployment, which is in
[serving cards](serving-cards.md).

## 3. Run the server

The fixture corpus lives in the test tree. It holds eight cards across two synthetic products
(`widget`, `gadget`) and two isolated clients (`alpha`, `beta`), and carries no real-world domain
vocabulary on purpose: it is a fair test that the card model is domain-neutral.

```bash
CONCEPTS_DIR=tests/fixtures/corpus/concepts \
CLIENTS_DIR=tests/fixtures/corpus/clients \
LEDGER_DSN=postgresql://hive:hive@127.0.0.1:5433/hive \
HOST=127.0.0.1 PORT=8099 \
uv run hiveserve serve --http
```

```
INFO:     Started server process [384530]
INFO:     Waiting for application startup.
StreamableHTTP session manager started
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8099 (Press CTRL+C to quit)
```

Leave `LEDGER_DSN` out and the server refuses to start, by design:

```
LEDGER_DSN is not set. The ledger is Postgres since 2026-08-19; there is no file fallback,
because falling back is how an empty ledger gets served as if it were the real one.
```

One line and exit 1, not a traceback. The same is true of `CONCEPTS_DIR`, which has no default
either - see [configuration](../reference/configuration.md#where-the-corpus-is).

## 4. Query it

In another terminal.

**Is it up:**

```bash
curl -s localhost:8099/healthz
# {"ok":true}
```

This answers "is the process alive" and nothing more. It reports `ok` even when the corpus is empty,
which has caused a real outage. See [metrics](../reference/metrics.md).

**What is in there:**

```bash
curl -s localhost:8099/concepts | python3 -m json.tool
```

```json
[
    {
        "id": "gadget/routing-rules",
        "title": "Gadget Routing Rules",
        "product": "gadget",
        "type": "concept"
    },
    {
        "id": "widget/assembly-process",
        "title": "Widget Assembly Process",
        "product": "widget",
        "type": "concept"
    },
    {
        "id": "widget/calibration-routine",
        "title": "Widget Calibration Routine",
        "product": "widget",
        "type": "concept"
    },
    {
        "id": "widget/widget-registry",
        "title": "WIDGET_REGISTRY",
        "product": "widget",
        "type": "dbobject"
    }
]
```

A lean index: ids, titles, products, types, and no card bodies. Four entries from eight cards,
because the index is shared knowledge only. The three client cards are absent - REST never loads
the clients tree - and so is the correction, which arrives attached to what it corrects rather than
as a thing you browse.

On a real corpus the index also omits the on-demand database-object tier at
`concepts/<product>/db/**`, which is usually most of the corpus and would swamp everything else.
The fixture's `dbobject` card is not in that tier, which is why you can see it here.

**Search it:**

```bash
curl -s "localhost:8099/find_concepts?q=calibration"
```

```json
[{"id":"widget/calibration-routine","title":"Widget Calibration Routine","product":"widget","description":"How a widget is calibrated after assembly, including the default tolerance and the recalibration interval."}]
```

Keyword search over ids, titles and descriptions, ranked by how rare the matched words are. No
embeddings, no model. A query made only of common words returns `[]` rather than the whole corpus:

```bash
curl -s "localhost:8099/find_concepts?q=the"
# []
```

See [hive-serve](../reference/hive-serve.md#search) for the scorer.

**Resolve a card, and watch the correction arrive with it:**

```bash
curl -s -X POST localhost:8099/resolve \
  -H 'Content-Type: application/json' \
  -d '{"ids":["widget/calibration-routine"]}' | python3 -m json.tool
```

The response is `{card_ids, bundle, dropped, corrections}`. `bundle` is the concatenated card
markdown, which is what an agent reads; the interesting part is the ids:

```json
{
    "card_ids": [
        "widget/calibration-routine",
        "widget/assembly-process",
        "widget/widget-registry",
        "widget/corrections/calibration-tolerance-restated"
    ],
    "dropped": [],
    "corrections": [
        "widget/corrections/calibration-tolerance-restated"
    ]
}
```

One card was asked for and four came back:

- the card itself
- two cards it links to through `related`, because `depth` defaults to 1
- **a correction**, which nobody asked for

The fixture corpus contains a correction stating that the calibration tolerance is 0.25 units
rather than the 0.5 the original card claims. The resolver attaches it automatically, so an agent
reading this bundle cannot see the outdated figure without also seeing the amendment.

That is the whole idea in one response. The original card is never edited, the amendment is
explicit and attributable, and both are in git.

Try flipping `status: approved` to `status: draft` in
`tests/fixtures/corpus/concepts/widget/corrections/calibration-tolerance-restated.md` and repeating
the call:

```json
{
    "card_ids": [
        "widget/calibration-routine",
        "widget/assembly-process",
        "widget/widget-registry"
    ],
    "corrections": []
}
```

The correction disappears from the bundle. A correction that is not approved is inert, which is a
useful thing to have seen once, because in a real corpus it looks exactly like a correction that is
working. Change it back before moving on.

## 5. What REST will not do

Client-scoped memory and issue cards are **not** reachable over REST. That door serves shared
knowledge only; scoped cards go through MCP, which carries an identity.

Asking for scoping over REST is an error rather than a quiet shared-only answer:

```bash
curl -s -X POST localhost:8099/resolve \
  -H 'Content-Type: application/json' \
  -d '{"ids":["clients/alpha/memory/calibration-override"],"client":"alpha"}'
```

```json
{"detail":[{"type":"extra_forbidden","loc":["body","client"],"msg":"Extra inputs are not permitted","input":"alpha"}]}
```

`422 Unprocessable Entity`. If that field were ignored you would get a 200 and a plausible answer,
with no way to tell that the isolation you asked for was never applied.

## 6. Connect an MCP client

Stop the HTTP server and run the MCP door instead:

```bash
CONCEPTS_DIR=tests/fixtures/corpus/concepts \
CLIENTS_DIR=tests/fixtures/corpus/clients \
LEDGER_DSN=postgresql://hive:hive@127.0.0.1:5433/hive \
uv run hiveserve serve --stdio
```

That is MCP over stdio, which is what most desktop and editor agents speak directly; Claude Desktop
and Claude Code are two of them, and nothing here is specific to any one vendor. `serve --http`
above was already serving the same MCP surface over streamable HTTP, mounted beside the REST
routes, for clients that prefer it.

Either transport exposes the same fifteen tools: retrieval, the work ledger, and personal memory.

```
list_concepts, find_concepts, get_card, resolve, find_db_objects,
start_objective, list_objectives, get_objective, append_entry, set_status, record_quiz_result,
remember, recall, forget, promote
```

Two things the REST door cannot do are visible here. Client context is one of them: MCP
`find_concepts` takes a `client` argument, and naming one adds that client's own memory to the
candidate set.

| Call | Returns, best first |
|---|---|
| `find_concepts(query="calibration")` | `widget/calibration-routine` |
| `find_concepts(query="calibration", client="alpha")` | `clients/alpha/memory/calibration-override`, `widget/calibration-routine` |

Alpha's own note that it calibrates to a tighter tolerance outranks the general card, and `beta`
never sees it. Note the parameter is `query` here and `q` on the REST route.

The ledger is the other. `start_objective(mode="investigate", goal="…")` opens a work stream in
Postgres, and `list_objectives()` reads them back as an array:

```json
[
  {
    "id": "32e770c2104e424b8609a4b823d22c63",
    "owner": "local-operator",
    "mode": "investigate",
    "goal": "why is calibration drifting",
    "status": "open",
    "external_ref": null,
    "visibility": "private",
    "created_at": "2026-09-06T06:01:37.171828+00:00",
    "updated_at": "2026-09-06T06:01:37.171828+00:00"
  }
]
```

`start_objective` and `get_objective` return one such object rather than an array, with an
`entries` list added.

`owner` is `local-operator` because stdio has no identity header and no gate in front of it. Over
HTTP it comes from the header named by `IDENTITY_HEADER`, and it is never a tool parameter. See
[the trust boundary](serving-cards.md#identity-and-what-it-is-not), which is the page to read
before exposing this to anyone.

## 7. Clean up

```bash
podman rm -f hive-demo-pg
```

## Next

- [Building a corpus](building-a-corpus.md) to point Hive at your own documents.
- [Serving cards](serving-cards.md) for identity, client isolation and the MCP surface.
- [Cards](../concepts/cards.md) for the format itself.

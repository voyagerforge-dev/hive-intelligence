# Getting started

Serve the bundled fixture corpus and query it. About five minutes, no credentials, no corpus of
your own, no model calls.

Every command and every output below was run against this repository.

## Prerequisites

Python 3.12 or later, and [uv](https://docs.astral.sh/uv/).

## 1. Install

```bash
cd tooling/hive-serve
uv sync --extra dev
```

## 2. Run the server

The fixture corpus lives in the test tree. It holds eight cards across two synthetic products
(`widget`, `gadget`) and two isolated clients (`alpha`, `beta`), and carries no real-world domain
vocabulary on purpose: it is a fair test that the machinery is domain-neutral.

```bash
CONCEPTS_DIR=tests/fixtures/corpus/concepts \
CLIENTS_DIR=tests/fixtures/corpus/clients \
OKF_DATA_DIR=/tmp/hive-demo \
HOST=127.0.0.1 PORT=8099 \
uv run hiveserve serve --http
```

`OKF_DATA_DIR` is where the SQLite work ledger goes. It is created on first use.

## 3. Query it

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
    }
]
```

A lean index: ids, titles, products, types. Not the card bodies, and not the database-object tier,
which is resolved on demand so a large schema cannot swamp the index.

**Search it:**

```bash
curl -s "localhost:8099/find_concepts?q=calibration"
```

```
widget/calibration-routine | Widget Calibration Routine
```

Keyword search over titles and descriptions. No embeddings, no scores, no ranker.

**Resolve a card, and watch the correction arrive with it:**

```bash
curl -s -X POST localhost:8099/resolve \
  -H 'Content-Type: application/json' \
  -d '{"ids":["widget/calibration-routine"]}'
```

```
card_ids:    ['widget/calibration-routine',
              'widget/assembly-process',
              'widget/widget-registry',
              'widget/corrections/calibration-tolerance-restated']
corrections: ['widget/corrections/calibration-tolerance-restated']
```

This is the interesting part. One card was asked for and four came back:

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
the call. The correction disappears from the bundle. A correction that is not approved is inert,
which is a useful thing to have seen once, because in a real corpus it looks exactly like a
correction that is working.

## 4. What REST will not do

Client-scoped memory and issue cards are **not** reachable over REST. That door serves shared
knowledge only; scoped cards go through MCP, which carries an identity.

Asking for scoping over REST is an error rather than a quiet shared-only answer:

```bash
curl -s -X POST localhost:8099/resolve \
  -H 'Content-Type: application/json' \
  -d '{"ids":["clients/alpha/memory/calibration-override"],"client":"alpha"}'
# 422 Unprocessable Entity
```

If that field were ignored you would get a 200 and a plausible answer, with no way to tell that the
isolation you asked for was never applied.

## 5. Connect Claude

Stop the HTTP server and run the MCP door instead:

```bash
CONCEPTS_DIR=tests/fixtures/corpus/concepts \
CLIENTS_DIR=tests/fixtures/corpus/clients \
OKF_DATA_DIR=/tmp/hive-demo \
uv run hiveserve serve --stdio
```

That is the transport Claude Desktop and Claude Code speak. It exposes fifteen tools: retrieval,
the work ledger, and personal memory. See [serving cards](serving-cards.md).

## Next

- [Building a corpus](building-a-corpus.md) to point Hive at your own documents.
- [Serving cards](serving-cards.md) for identity, client isolation and the MCP surface.
- [Cards](../concepts/cards.md) for the format itself.

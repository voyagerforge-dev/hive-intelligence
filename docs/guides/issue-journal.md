# Issue journal

`hive-zendesk` distils **closed** support tickets into client-scoped `issue` cards, so that a
problem seen once at a client is recognised the next time rather than rediscovered.

The question it makes answerable is "has this happened at this client before, and what fixed it".
Without it, that knowledge sits in a ticketing system nobody searches and in the memory of whoever
handled it.

## Prerequisites

An HTTP endpoint that serves closed tickets, addressed by `CONNECTOR_BASE`. This has no default:
the address belongs to a deployment, and a plausible-looking default fails late and against the
wrong host.

A model gateway, for distillation.

A `customers.yaml` mapping your client keys to their ticket-system organisation ids. That file is
corpus-side, because it names your clients.

## Modes

```bash
uv run hivezendesk <mode> --client <key> --customers <path> \
  --clients-dir <path> --concepts-dir <path> --state-dir <path>
```

| Mode | Does |
|---|---|
| `backfill` | first run, over all available history |
| `incremental` | since the last recorded run |
| `rebuild` | re-distil existing cards without re-fetching them, for example after a prompt change |
| `relink` | recompute links from issue cards to concept cards, without re-distilling |

**All four call a model**, so all four cost something. `rebuild` and `relink` exist because the two
model stages fail independently: a bad linking pass is repairable without redoing the distillation,
which is the expensive half. Neither is a free operation.

## Dry-run first, every time

```bash
uv run hivezendesk backfill --client <key> ... --dry-run
```

`--dry-run` fetches and gates but makes no model calls and writes no cards. A real backfill is one
model call per entry, so sizing it first is the difference between a known cost and a surprise.

## Two failure modes worth knowing

**Closed tickets only, with lag.** The tool reads closed tickets. If your ticket system closes
tickets on a delay, recent problems are invisible until they close, and that lag can be weeks. An
empty result does not mean nothing happened.

**Source truncation is silent.** Ticket APIs cap results, and a capped response looks exactly like
a complete one. `hive-zendesk` warns when a pull approaches the configured cap
(`CONNECTOR_PAGE_CAP`, warning at `CAP_WARN_RATIO`), because a short page is not proof there is no
more data. Treat the warning as "this run is incomplete", not as noise.

## What comes out

Cards under `clients/<client>/issues/`, typed `issue`, linked to the concept cards they relate to.
Their retrieval rules are in [the resolver reference](../reference/hive-serve.md#the-resolver),
not an identity-based prohibition on reading another client's history; see
[the serving trust boundary](serving-cards.md#identity-and-what-it-is-not).

The link back to concepts is what makes them useful: an agent resolving a concept card can see that
this exact area has caused a specific problem at this specific client.

## Scrubbing

Ticket text contains customer data. `hive-zendesk` scrubs identifiers before anything reaches the
model or a card.

The scrub patterns are tuned to the identifier formats that appear in a given corpus, such as
national identity numbers of a particular country's format. **Check that the patterns match your
data before a first real run.** A scrubber tuned for one country's identifier format offers no
protection against another's, and it will not tell you it is not matching.

## Scheduling

There is none here. Running this monthly, or nightly, or never, is a deployment decision, and Hive
ships the tool rather than the cron.

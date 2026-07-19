# okf-zendesk

Distils **closed** Zendesk tickets for ALPHA and BETA into client-scoped OKF **issue cards**, so the
Diagnose skill can answer "has this happened at this client before?".

Design: `knowledge/okf/docs/superpowers/specs/2026-07-19-okf-zendesk-issue-cards-design.md`

## ⚠ Before you run this

A real run **spends money** (one LLM call per surviving ticket) and **writes cards** into
`knowledge/okf/clients/<client>/issues/`. Always size it with `--dry-run` first.

```bash
# costs nothing: fetches and gates, but never calls the model and never writes
okfzendesk backfill --client alpha --client beta \
  --customers /srv/reference/customers.yaml \
  --clients-dir knowledge/okf/clients \
  --concepts-dir knowledge/okf/concepts \
  --state-dir knowledge/okf/tooling/okf-zendesk/state \
  --dry-run
```

The dry-run prints `fetched / emitted(would) / skipped` plus the first 20 skip reasons. Use it to
decide whether the value gate needs tightening before spending.

## Closed, not solved

The connector serves `status:closed` only - solved tickets are excluded by contract because they are
reopenable. Consequences:

- **Backfill:** no loss. Anything solved long ago is closed by now.
- **Monthly incremental:** trails by the Zendesk auto-close window (~28 days).

The status filter is a parameter, not hardcoded, so adding a `solved` route to the connector later
is a one-argument change here. That route is a change to a live service and is out of scope.

## Pipeline

```
fetch -> gate -> scrub -> distil -> link -> emit -> verify
```

- **fetch** - read-only, via `connectors/zendesk-connector` (never Zendesk directly). ALPHA is 1 org,
  BETA is 7, so a client pull fans out and merges.
- **gate** - deterministic, pre-LLM, so noise costs nothing. Drops thin content, noise patterns
  (password/access requests), threads with no agent diagnosis, and near-duplicates. Every drop is
  logged with a reason.
- **scrub** - strips names, emails, phones and **13-digit SA ID numbers** before the model sees
  the thread. A card that still trips the detector is **quarantined, not written**, and the run
  continues (`pii_held` in the report).
- **distil** - one LLM call per ticket, strict schema; returns nothing rather than a half-card.
- **link** - `related` ids are kept only if they resolve to a real card. Never invented.
- **emit** - idempotent; a ticket is bound to one file by id prefix even if the title is reworded.
- **verify** - hard gate; any failure raises and the run fails.

## Safety properties (all test-covered)

| Property | Enforced by |
|---|---|
| No personal data in a card | scrub before the LLM; `leaks()` checked before writing, card quarantined if it hits |
| PII never reaches logs | `leaks()` returns *kinds* (`email`, `phone`, `sa_id`, `known-name`), never values |
| One leaky card cannot kill a backfill | quarantine + continue, reported as `pii_held` |
| No repeat spend | a ticket already carded is not re-fetched or re-distilled |
| No silent truncation | connector caps at 3000 and does not error; an at-cap result raises instead |
| Human edits survive | `status: approved` cards are never overwritten without `--force` |
| No invented citations | unresolvable `related` candidates are dropped, and the gate rejects any that remain |
| Counts reconcile | `fetched == emitted + skipped + preserved + cached + pii_held + failed` |
| One ticket, one card | existing card found by ticket-id prefix, not by title slug |

## Environment

```
CONNECTOR_API_KEY=...    # shared with kantata-connector
BIFROST_BASE=...
BIFROST_API_KEY=...
```

The connector resolves Zendesk credentials itself via Nango. A machine caller omits the identity
header and is served by the **service connection** - if that is unset the connector returns 503.

## Tests

```bash
python -m venv .venv && ./.venv/bin/pip install -e '.[dev]'
./.venv/bin/python -m pytest tests/ -q
```

No test touches a live API or a real model.

## Scheduling (not yet deployed)

Intended: a monthly Windmill job running `okfzendesk incremental` for both clients, following the
`cards_sync` pattern. **Deliberately not created** - it touches live infrastructure and spends on
distillation, so it needs explicit approval.

## Status

Built and tested. **Never yet run against live Zendesk.** Outstanding before a first real run:
a counting dry-run to size the backfill and its cost, and a decision on the review sample rate.

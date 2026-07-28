# hive-zendesk

Closed support tickets to client-scoped issue cards. Package `hivezendesk`, CLI `hivezendesk`.

Narrative version: [issue journal](../guides/issue-journal.md).

## What an issue card is, and is not

An issue card is **not** a knowledge card. The concept corpus already explains how the product
behaves; restating that per ticket would duplicate it thousands of times and dilute retrieval.

An entry records three things:

- **what happened** at this client, in one sentence
- **how it closed**, in one sentence
- **where**: a module, plus `related` links to the concept cards that explain the behaviour

Its job is to make someone *aware* that an area has bitten this client before. The explanation
lives in the card it points at. An entry is an awareness flag, never a root cause.

## Modes

```bash
hivezendesk <mode> --client <key> --customers <path> \
  --clients-dir <path> --concepts-dir <path> --state-dir <path> [--dry-run]
```

| Mode | Does |
|---|---|
| `backfill` | first run, over available history |
| `incremental` | since the last recorded cursor |
| `rebuild` | re-distil existing staged cards, for example after a prompt change |
| `relink` | recompute `related` links only, no distillation |

Other options: `--force`, `--limit`, `--workers`, `--batch-size`, `--model`.

**`--dry-run` fetches and gates but makes no model calls and writes nothing.** A real backfill is
one model call per entry. Size it first.

## Two models, two jobs

The **distiller** writes the prose. The **reranker** chooses the concept links. Configured
separately (`DISTILL_MODEL`, `RERANK_MODEL`), because linking is a different task from summarising
and is measured separately.

## Modules

| Module | Purpose |
|---|---|
| `fetch.py` | connector client, GET only. Raises at the page cap rather than truncating silently |
| `gate.py` | deterministic pre-model gate: is this ticket worth distilling at all |
| `scrub.py` | strip personal data before the model; `leaks()` afterwards reports kinds, never values |
| `distill.py` | ticket thread to entry, for `backfill` and `incremental` |
| `reshape.py` | existing staged card to entry, for `rebuild`; supports batching |
| `relink.py` | lexical shortlist then model rerank, producing `related`, the product facet and `linked_by` |
| `emit.py` | render and write cards. Idempotent, never overwrites an approved card |
| `verify.py` | per-card gate and per-run count reconciliation |
| `fm.py` | frontmatter parsing that survives `---` appearing inside a value |
| `r2.py` | read staged cards from object storage |
| `rebuild.py` | orchestrate the staged path: index, concurrent reshape, write |
| `state.py` | per-client cursors for incremental runs |
| `orgs.py` | client key to ticket-system organisation ids, from `customers.yaml` |
| `model.py` | `Ticket`, `IssueCard`, `RunReport`, `RunError` |
| `llm.py` | chat client with defensive JSON extraction |
| `config.py` | typed settings |
| `run.py` | CLI orchestration |

## Safety properties

**The ticket system is read-only.** All access is GET through a connector. The tool never writes
back.

**Personal data is handled on both sides.** Scrubbed before the model, asserted after. A hit
**quarantines that one card and continues**, rather than aborting a run of several hundred tickets.
`leaks()` returns kinds and never values, because its output lands in logs and run reports.

**Identifier detection is structural, not a digit count.** The scrubber validates an identifier's
internal structure, including a check digit where the format has one. A bare digit-length match
flagged ordinary domain identifiers such as container, wave and item numbers, and withheld
legitimate cards.

> Patterns are tuned to specific identifier formats. **Check they match your data before a first
> real run.** A scrubber that matches nothing offers no protection and does not say so.

**Closed tickets are immutable**, so a ticket already carded is never re-fetched or re-distilled.
That is what makes replaying a window cheap.

**Counts must reconcile** at end of run: everything fetched must be accounted for as emitted,
skipped, preserved, cached, held or failed. A run that cannot account for every ticket fails.

**Approved cards are never overwritten** unless `--force` is passed.

## Configuration

See [configuration](configuration.md#hive-zendesk).

`CONNECTOR_BASE` and `DISTILL_MODEL` have **no default** and are validated at startup. The second
matters more than it looks: an environment that silently fails to load its `.env` would otherwise
distil an entire run with an unintended model, and the cards would carry no record of it.

## Known limits

**Link precision is around 85%** with a cheap reranker, and around 92% with a frontier model. The
residual failure has a consistent shape: a card in the right functional area that does not explain
the specific mechanism.

**The reranker is not fully deterministic.** Re-running can produce different links for
near-identical entries.

**Roughly a fifth of entries carry no link at all, by choice.** A wrong reference misleads more
than a missing one helps.

**Closed tickets only, with lag.** If your ticket system closes on a delay, a monthly run must look
back further than a month or it will skip tickets.

**Truncation is silent at the source.** A capped API response looks exactly like a complete one.
`CAP_WARN_RATIO` warns near `CONNECTOR_PAGE_CAP`; treat that warning as "this run is incomplete".

## Worth doing

Carried forward from the original notes, because they are real and unfixed.

- **`incremental` has never run against live data.** Corpora built so far went through `rebuild`.
  Dry-run, then `--limit 5`, before anything runs unattended.
- **Stamp the model from the response, not from configuration.** A gateway returns the resolved
  upstream model; without reading it, a card distilled during a fallback claims to be something it
  is not.
- **Distiller fallback on transport failure only.** A single-box model backend fails identically for
  every call and takes a whole batch with it. Falling back on a bad *answer* would be worse than
  failing.
- **A golden set and a precision gate.** Precision is not observable at runtime; measuring it needs
  labels. Freeze a few dozen entries with confirmed links and score them each run.
- **Domain review.** Structural properties are verified by tests. Whether the summaries are *true*
  is not, and no test can tell you.

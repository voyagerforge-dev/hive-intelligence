# OKF tooling - okf-zendesk (`okfzendesk`)

*Distils closed Zendesk tickets into client-scoped **journal entries** - the incident history that the Diagnose / Plan / Learn skills consult. Conceptual model in [OKF-Pipeline.md](../OKF-Pipeline.md).*

**Tooling reference:** [Hub](README.md) · [okf-prep](okf-prep.md) · [okf-gen](okf-gen.md) · [okf-serve](okf-serve.md) · [okf-dbparse](okf-dbparse.md) · [okf-author](okf-author.md) · **okf-zendesk** · [Architecture & Concepts](../OKF-Pipeline.md)

`okfzendesk` turns resolved support tickets into one thin `type: issue` card per ticket under `clients/<client>/issues/`. All LLM calls go through Bifrost. Two different models do two different jobs: the **distiller** writes the prose (on-prem `host-d/qwen3.6-27b`), and the **reranker** chooses the concept-card links (`minimax-m3` by default).

## What a journal entry is - and is not

A journal entry is **not** a knowledge card. The concept corpus already explains how WMOS behaves; restating that per ticket would duplicate it thousands of times and dilute retrieval. An entry records only:

- **what happened** at this site, in one sentence
- **how it closed**, in one sentence
- **where** it happened: `module`, plus `related` links to the concept cards that explain the behaviour

Its job is to make a consultant *aware* that an area has bitten this client before. The explanation lives in the card it points at. The skills state this contract explicitly: an entry is an awareness flag, never a root cause.

## Pipeline

```
fetch -> gate -> scrub -> distil -> PII quarantine -> emit -> verify -> relink
```

**Linking comes last, and deliberately so.** The distiller has never seen the corpus, so any card id it produces is a guess - measured at a 4% resolution rate on the first build. Cards are therefore emitted with `related: []` and linked afterwards against real card ids, by a model that is shown a candidate shortlist and is free to decline.

## Modes

| Mode | Source | Use |
|---|---|---|
| `backfill` | Zendesk connector, full history | first build for a client |
| `incremental` | Zendesk connector, since saved cursor | the monthly run |
| `rebuild` | staged cards on Cloudflare R2 | re-derive entries without re-reading ticket threads |
| `relink` | cards already on disk | re-run linking only, e.g. to escalate to a stronger model |

All modes except `relink` run the relink stage automatically (`skip_linked=True`, so only new entries cost anything).

## Module index

| Module | Purpose |
|---|---|
| `fetch.py` | Zendesk **connector** client (never Zendesk directly). Raises at the 3000-row page cap rather than truncating silently. |
| `gate.py` | Deterministic pre-LLM value gate: is this ticket worth distilling at all. |
| `scrub.py` | Strip PII before the LLM; `leaks()` afterwards reports PII **kinds, never values**. |
| `distill.py` | Ticket thread -> journal entry (used by `backfill` / `incremental`). |
| `reshape.py` | Existing staged R2 card -> journal entry (used by `rebuild`); supports batching. |
| `relink.py` | Lexical shortlist + model rerank -> `related` links, product facet, `linked_by`. |
| `emit.py` | Render and write cards. Idempotent; never overwrites a human-approved card. |
| `verify.py` | Per-card gate (schema, `sources.ref`, PII) and per-run count reconciliation. |
| `fm.py` | Frontmatter parsing that survives `---` appearing inside a value. |
| `r2.py` | Read staged cards from the shared R2 bucket; strict key parsing. |
| `rebuild.py` | Orchestrate the R2 path: index -> concurrent reshape -> write. |
| `state.py` | Per-client, per-org cursors for incremental runs. |
| `orgs.py` | Client -> Zendesk org ids, from `reference/customers.yaml`. |
| `model.py` | `Ticket`, `IssueCard`, `RunReport`, `RunError`. |
| `llm.py` | Bifrost chat client + defensive JSON extraction. |
| `config.py` | Typed settings: connector, Bifrost, R2, **`distill_model`**, **`rerank_model`**. |
| `run.py` | CLI orchestration and the four modes. |

## How linking works

Two stages, because 990 concept cards is too many to put in front of a model.

**1. Lexical shortlist** (no model, milliseconds). The entry's title, description, module and tags are tokenized - lowercased, stopwords dropped, plurals folded so `doors` matches `dock-door-management`. Each concept card is tokenized from its id and title. Score is the fraction of *the card's own* IDF mass the entry covers, which is scale-free, so the threshold means the same thing on any corpus size. Guards: >= 2 shared tokens, score >= 0.18, top 10. This stage is tuned for **recall** and is deliberately noisy.

**2. Model rerank.** The model sees 10 ids with their titles and picks 0-2, with "none" stated as a correct answer. This stage is tuned for **precision**. Its picks are filtered against the offered list (it cannot invent a card), capped at 2, and confined to a single product. It **fails closed**: an unparsable reply, an empty reply, or a refusal all produce no link.

Only `type: concept` cards are link targets. The corpus is 88% `dbobject` cards, and pointing a consultant at `ALLOC_PARM` does not explain behaviour.

### Product facet

Candidates are drawn from all products, and the model's first pick determines the entry's own `product`. Two guards keep this honest:

- links are **confined to one product**, so cross-product edges - which OKF forbids - are impossible by construction
- leaving `wms` requires **positive evidence in the entry's own words** (`cognos`, `sci`, `slotting`, `payroll`...). Inferring product from the picked card alone filed "WMOS Application is down" under Slotting. A wrong facet is worse than a wrong link, because OKF *selects* on product: a WMS entry stamped `slotting` is invisible to a WMS-scoped consultant.

## Model selection and measured quality

| Setting | Default | Job |
|---|---|---|
| `distill_model` | `host-d/qwen3.6-27b` (via `.env`) | writes the prose |
| `rerank_model` | `minimax-m3` | chooses the links |

Rerank quality, measured on a 16-item labelled set (12 known-good links, 4 known-bad):

| Model | good kept | bad kept | precision |
|---|---|---|---|
| `host-d/qwen3.6-27b` | 12/12 | 3/4 | ~80% |
| `minimax-m3` | 12/12 | 3/4 | ~80% |
| `deepseek-v4-flash` | 11/12 | 3/4 | ~79% |
| `claude-sonnet-5` | 10/12 | 3/4 | ~77% |
| **`claude-opus-4-8`** | 11-12/12 | **1/4** | **~92%** |

**This is a capability cliff, not a gradient.** Every cheap model keeps the *same* three wrong links; only Opus rejects them. Three stricter prompt variants were tested and moved nothing - prompting does not reach past it.

So the cheap tier is the default, and Opus is an on-demand escalation:

```bash
okfzendesk relink --client alpha --clients-dir ../../clients --concepts-dir ../../concepts \
  --model openrouter/claude-opus-4-8
```

At ~$0.0033/entry, a full 2,295-entry Opus pass costs about $6.60 and takes ~7 minutes.

## Provenance

Every card records both models, because they are not the same and the distinction matters:

```yaml
model:      host-d/qwen3.6-27b             # wrote the prose
linked_by:  openrouter/claude-opus-4-8   # chose the links
```

## Safety properties

- **Zendesk is read-only.** All access is via the connector (GET only); the tool never writes to Zendesk.
- **PII is two-sided.** Scrubbed before the LLM, asserted after. A hit **quarantines that one card and continues** rather than aborting a several-hundred-ticket run. `leaks()` returns kinds, never values, because the result lands in logs and run reports.
- **SA ID detection is structural** - a valid `YYMMDD` prefix plus a Luhn check digit. A bare 13-digit match flagged WMS identifiers (LPN, wave and item numbers) and withheld legitimate cards.
- **Closed tickets are immutable**, so a ticket already carded is never re-fetched or re-distilled. This is what makes a replayed window cheap.
- **Counts must reconcile**: `fetched == emitted + skipped + preserved + cached + pii_held + failed`, enforced at end of run.
- **Human-approved cards are never overwritten** (`status: approved` is preserved unless `--force`).

## Running it

```bash
# size and cost a backfill without spending anything
okfzendesk backfill --client alpha --dry-run \
  --customers ../../../../reference/customers.yaml \
  --clients-dir ../../clients --concepts-dir ../../concepts --state-dir ./state

# the monthly run
okfzendesk incremental --client alpha --client beta \
  --customers ../../../../reference/customers.yaml \
  --clients-dir ../../clients --concepts-dir ../../concepts --state-dir ./state
```

`--dry-run` fetches and gates but never calls the LLM and never writes.

### Deploying the result

Cards are served by `okf-serve` from a git checkout on Host-A, refreshed by the Windmill `cards_sync` job. **A card change reaches consultants only after it is merged to `main`** and that job runs. Note that `cards_sync` refreshes *data* only - anything touching `okfserve` code needs an image rebuild.

## Known limits

- **Link precision is ~85%** with the cheap reranker (~92% with Opus). The residual failure is consistently the same shape: a card in the right functional area that does not explain the specific mechanism.
- **The reranker is not fully deterministic.** Re-running can produce different links for near-identical entries, though a 3-trial check reproduced 12/12 known-good links each time, so it is more stable than early anecdotes suggested.
- **~20% of entries carry no link at all**, by choice. A wrong reference misleads more than a missing one helps.
- **`routine` means "a routine scheduled request rather than a fault"** - it is *not* a recurrence count. The ALPHA/BETA split (30% vs 3%) is believed to be a real engagement difference, unverified.
- **The connector serves `closed` tickets with a ~28-day lag**, so a monthly run must look back further than one month or it will skip tickets.

## TODO

Ordered by what blocks an unattended monthly run.

- [ ] **Exercise `incremental` against live data.** The entire corpus was built via `rebuild` (R2 -> `reshape.py`). The `incremental` path (`distill.py`, live ticket threads, 6000-char truncation) has only ever run against fakes. Do a `--dry-run`, then `--limit 5`, before anything runs unattended.
- [ ] **Windmill monthly schedule.** No job exists. Mirror `f/example/okf/cards_sync`; account for the ~28-day connector lag in the look-back window.
- [ ] **Distiller fallback.** Host-D is a single box; when it is down every call fails identically and a batch dies with it. Add a client-side `FallbackChat` (primary -> `deepseek-v4-flash`) that falls back on *transport* failure only, not on a bad answer, and logs a `fell_back` count. Bifrost's own circuit breaker is enterprise-only.
- [ ] **Stamp `model:` from the response, not the config.** Bifrost returns the resolved upstream model; without this a card distilled during a fallback would claim to be Qwen.
- [ ] **`distill_model` should have no default.** It currently defaults to `minimax-m3`, so an environment that does not load `.env` silently distils with a different model instead of failing.
- [ ] **Golden set + precision gate.** Precision is not observable at runtime - measuring it needs labels. Freeze ~40 entries with human-confirmed links, score them each month with the cheap reranker, and escalate that month's entries to Opus when precision drops below threshold. The 16 labels used above are one engineer's judgement and should be human-confirmed before they gate spending.
- [ ] **Domain review of the corpus.** 2,295 entries are live and no domain reader has confirmed the summaries are true or the links useful. Structural properties are verified; correctness is not.
- [ ] **REST surface does not serve client cards.** `/concepts` never passes `clients_dir` and takes no `client` parameter, so memory and issue cards are invisible over REST. MCP is unaffected, which is what consultants use.

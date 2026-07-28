# Metrics

`hive-serve` exposes Prometheus metrics at `GET /metrics`. No authentication, so treat the endpoint
as internal.

## What is exposed

### HTTP

| Metric | Type | Labels |
|---|---|---|
| `http_requests_total` | counter | `endpoint`, `method`, `status` |
| `http_request_duration_seconds` | histogram | `endpoint`, `method` |

`endpoint` is a bounded set: `/healthz`, `/concepts`, `/resolve`, `/card/{id}`. The `/mcp` mount and
unknown paths are not measured, which keeps cardinality fixed. `/metrics` excludes itself
deliberately: counting Prometheus scraping would dilute the denominator of any error-rate alert.

### MCP

| Metric | Type | Labels |
|---|---|---|
| `mcp_tool_calls_total` | counter | `tool`, `outcome` |
| `mcp_tool_duration_seconds` | histogram | `tool` |

`outcome` is `ok` or `error`.

### Corpus

| Metric | Type | Labels |
|---|---|---|
| `okf_corpus_cards` | gauge | `product`, `regime` |
| `okf_corpus_db_objects` | gauge | `product` |
| `okf_ledger_rows` | gauge | `table` |

Both corpus gauges are needed to see the whole corpus, and this is the important thing on this page.

`okf_corpus_cards` counts **indexed** cards. It deliberately excludes the database-object tier,
because that tier is resolved on demand and is excluded from the index. On a corpus with a real
schema behind it, that exclusion is most of the corpus: 7,249 of 10,536 cards in the deployment
this was measured on.

So `okf_corpus_db_objects` exists to cover the rest. An alert built on `okf_corpus_cards` alone
would report a healthy corpus while 88% of it was missing, which is worse than no alert at all,
because it turns silence into assurance.

There is **no `client` label anywhere**, by rule. Client names in metrics would leak the client list
to anyone who can read the endpoint, and would make cardinality grow with the customer base.

Corpus gauges are recomputed at most once every 30 seconds and cached, so a scrape never walks the
whole corpus. If the sample fails, the last known good values are served rather than the endpoint
breaking.

## What to alert on

### Not `/healthz`

`/healthz` reports that the process is alive. It says nothing about the corpus. A service whose
corpus mount has gone stale answers `{"ok":true}` and serves zero cards.

This is not theoretical. It caused an outage of about two hours during which every health check was
green.

### Alert on the card count

```yaml
- alert: HiveServeCorpusEmpty
  expr: (sum(okf_corpus_cards{job="hive_serve"}) or vector(0)) == 0
  for: 10m
  labels: { severity: critical }

- alert: HiveServeDbObjectsEmpty
  expr: (sum(okf_corpus_db_objects{job="hive_serve"}) or vector(0)) == 0
  for: 10m
  labels: { severity: critical }

- alert: HiveServeCorpusShrank
  expr: sum(okf_corpus_cards{job="hive_serve"})
        < 0.8 * sum(okf_corpus_cards{job="hive_serve"} offset 1h)
  for: 15m
  labels: { severity: warning }
```

**`or vector(0)` is load-bearing.** Without it, a series that disappears entirely returns no data,
the comparison has nothing to evaluate, and the rule never fires. That is precisely the failure
being guarded against: the corpus vanishing takes the metric with it. Confirm both branches when
you install these, because a rule that cannot fire looks identical to a rule that is not firing.

The shrink rule is a warning rather than a page. Bulk corrections and product removals are
legitimate, and a fifth of the corpus disappearing in an hour is worth a look rather than a
call-out.

### The rest

| Alert | Expression sketch |
|---|---|
| service down | `up{job="hive_serve"} == 0` |
| error rate | 5xx ratio over 5m above 5% |
| latency | p95 of `http_request_duration_seconds` above 1.5s |

## What is not measured

Cache hit rates, per-client anything, and card-level access counts.

The last one is a deliberate omission rather than an oversight. Recording which cards each identity
reads would build a usage profile of individuals inside client engagements, which is a thing worth
not having.

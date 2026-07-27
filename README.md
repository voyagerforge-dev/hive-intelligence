# Hive Intelligence

The knowledge system behind [VoyagerForge](https://voyagerforge.dev). Turns an
organisation's scattered institutional expertise into a curated, citable corpus that both
people and AI tools can answer from, with each client's knowledge isolated from every
other client's.

**OKF is the format. Hive is the system.** Cards on disk stay `okf_version: "0.1"`; the
tooling that produces and serves them is Hive.

## Tooling

| Package | Distribution | What it does |
|---|---|---|
| `tooling/hive-prep` | `vf-hive-prep` | Document ingestion, conversion and staging |
| `tooling/hive-gen` | `vf-hive-gen` | Distils documents into cards, and the card model |
| `tooling/hive-dbparse` | `vf-hive-dbparse` | Turns SQL DDL into database-object cards |
| `tooling/hive-zendesk` | `vf-hive-zendesk` | Turns closed support tickets into issue cards |
| `tooling/hive-serve` | `vf-hive-serve` | Resolver, client isolation, corrections, memory, MCP surface |
| `tooling/hive-author` | `vf-hive-author` | Files memory and correction cards as reviewable issues |

`ops/` holds the scheduled jobs: corpus sync, the memory conflict gate, and the ledger backup.

## The corpus lives elsewhere

This repository contains **no cards**. A corpus is the output of pointing Hive at a
particular organisation's documents, so it belongs to that organisation and lives in its
own repository. `hive-serve` is configured with a path to one.

For tests and demonstration, `tooling/hive-serve/tests/fixtures/corpus` holds a small
synthetic corpus: every card type, a curated link graph, two isolated clients, and a wired
corrections override. It deliberately carries no real-world domain vocabulary, which is
what makes it a fair check that the machinery is domain-neutral.

## Tests

Each package is independent. From any package directory:

```
uv sync && uv run pytest -q
```

Assertions that depend on a live corpus, or on the GitHub card-submission surface, skip
with a reason when their subject is not present. That is expected, not a failure.

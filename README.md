# Hive Intelligence

Curated knowledge, served to an AI agent as cards rather than retrieved as chunks.

Hive turns a body of documentation into a reviewed, cross-linked set of small markdown files in
git, then serves those files to Claude over REST and MCP. There is no vector index, no embedding
model, and no model call at serving time. The agent is the reasoning loop; Hive decides what it is
allowed to reason over.

**OKF is the format. Hive is the system.** Cards on disk carry `okf_version: "0.1"`; the tooling
that produces and serves them is Hive.

## Why cards instead of chunks

**Retrieval-augmented generation (RAG)** answers "which chunks look similar to this question". That
is a different question from "what is true here", and the gap between them is where confident wrong
answers come from. A chunk is an accident of where a document happened to be split, and it carries
no claim that anyone has ever checked it.

A card is the opposite. One concept, written once, reviewed by a person, versioned in git, and
addressable by a stable id. When it goes out of date it is corrected in the open by a card that
overlays it, leaving the original readable. What the agent sees is what a human approved.

The cost is honest: someone has to curate. Hive's job is to make that cheap enough to sustain, by
putting a model in front of every stage and a human gate behind it.

**You do not have to choose.** Hive also works as an ingestion stage *in front of* an existing RAG
system, because a card is already a chunk: one reviewed concept, no boilerplate, no accidental
split. If your RAG system underperforms, the cause is more often the corpus than the ranker, and
that is measurable before you change anything. See
[using Hive alongside an existing RAG system](docs/guides/alongside-rag.md).

## What is here

Six Python packages under `tooling/`. Three form the pipeline; three extend it.

| Package | Distribution | Does |
|---|---|---|
| `hive-prep` | `vf-hive-prep` | raw documents to clean atomic markdown |
| `hive-gen` | `vf-hive-gen` | atomic markdown to reviewed concept cards, and the card model |
| `hive-serve` | `vf-hive-serve` | serves cards over REST and MCP, with a per-person work ledger |
| `hive-author` | `vf-hive-author` | a write-only door for filing corrections and memory, so `hive-serve` holds no credentials |
| `hive-dbparse` | `vf-hive-dbparse` | database schema to cards, deterministically, with no model involved |
| `hive-zendesk` | `vf-hive-zendesk` | closed support tickets to client-scoped issue cards |

## Start here

- **[Documentation](docs/README.md)** is the map.
- **[Getting started](docs/guides/getting-started.md)** has `hive-serve` answering questions from
  the bundled fixture corpus in about five minutes.
- **[Architecture](docs/concepts/architecture.md)** is the conceptual reference.

## What this repository is not

It contains **no deployment and no corpus**, and both omissions are deliberate.

A file that names a host, an address or a mount path describes one installation rather than the
product, so it lives with that installation. A corpus is the output of pointing Hive at a
particular organisation's documents, so it belongs to that organisation and lives in its own
repository; `hive-serve` is given a path to one at runtime.
[The boundary](docs/architecture/product-deployment-boundary.md) sets out the rule and why it is
enforced rather than encouraged.

The only cards here are the synthetic fixtures under
`tooling/hive-serve/tests/fixtures/corpus`: every card type, a curated link graph, two isolated
clients, and a wired corrections override. They deliberately carry no real-world domain
vocabulary, which is exactly what makes them a fair check that the machinery is domain-neutral.

## Tests

Each package is independent. From any package directory:

```
uv sync --extra dev && uv run pytest -q
```

Assertions that depend on a live corpus, on its evaluation datasets, or on the GitHub
card-submission surface skip with a stated reason when their subject is absent. In this
repository they are expected to skip. In a deployment that has a corpus, they run.

## Licence

[Apache License 2.0](LICENSE). Use it, run it, modify it, redistribute it, build a product on
it. The licence includes an express patent grant.

**The licence covers the software, not any corpus.** A corpus belongs to whoever produced it and
ships separately; see [NOTICE](NOTICE).

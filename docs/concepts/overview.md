# Overview

## The problem

An organisation's working knowledge is scattered across vendor manuals, release notes, support
tickets, database schemas and the heads of the people who have been there longest. When someone
needs an answer, they ask a colleague, or they search, or they guess.

Handing that pile to a language model does not fix it. **Retrieval-augmented generation (RAG)**
answers a question the organisation did not ask: *which passages resemble this query*. Resemblance
is not truth. A passage can be perfectly on-topic and three years out of date, or contradicted by a
later decision nobody wrote down, or correct for one client and wrong for another. The model has no
way to tell, so it answers confidently either way.

The failure is not the model. It is that nothing in the pipeline ever asserted that a given
statement was true, current, and applicable here.

## The approach

Hive inverts the order. Instead of indexing everything and hoping the ranker sorts it out, it
distils documents into **cards**: one concept each, small enough to read, reviewed by a person
before entering the corpus, and stored as plain markdown in git.

At serving time there is no model, no embedding, and no vector index. The agent asks for concepts
by id, or searches a lean index of titles and descriptions, and gets back exactly the cards a human
approved. The reasoning happens in the agent. The judgement about what is true happened earlier,
and left an audit trail.

```
documents  ──►  atomic markdown  ──►  concept cards  ──►  Claude
            hive-prep          hive-gen           hive-serve
              gate 1            gates 2 and 3
```

Three things follow from this that are worth stating plainly.

**It is slower to build.** Curation is real work. Hive puts a model in front of every stage so a
person is reviewing a proposal rather than writing from scratch, but a person still reviews.

**It is much cheaper to run.** Serving is file reads. No vector database, no embedding calls, no
reranker. The only model calls in the whole system happen during content creation.

**It degrades honestly.** If a card is missing, the agent gets nothing rather than something
plausible. That is the intended behaviour: a gap you can see beats an answer you cannot check.

## Two ways to use it

Hive is usually read as an alternative to RAG. It is also useful as a stage in front of one, and
that is the smaller commitment.

**As the system.** Cards are served directly to an agent by id, with corrections attached. No
embeddings, no vector store, no model. Deterministic and auditable.

**In front of an existing RAG system.** Hive replaces ingestion and leaves retrieval alone. A card
is already a chunk: one reviewed concept, deduplicated, with boilerplate stripped and no accidental
split mid-idea. Your embedder and index stay exactly as they are.

The second mode matters because RAG systems usually underperform for reasons ranking cannot fix. In
one measured baseline over 40 labelled questions, adding a reranker changed hit-rate by **zero**,
while **27.5% of expected documents were never retrieved at all**, at any depth. That is a corpus
problem, and it is upstream of anything a ranker can influence.

Whether it is *your* problem is measurable in an afternoon, before you change anything. See
[using Hive alongside an existing RAG system](../guides/alongside-rag.md).

## Who this is for

Hive suits a body of knowledge that is **large enough to be unmanageable but stable enough to be
worth curating**, where being wrong is expensive. Product documentation for complex operational
software is the case it was built for. Legal, clinical and regulatory material have the same shape.

It suits you badly if the content changes faster than anyone can review it, if nobody owns
correctness, or if approximately-right answers are good enough. In those cases ordinary retrieval
is cheaper and the curation overhead buys nothing.

## What a card looks like

```markdown
---
okf_version: "0.1"
type: concept
title: Excess wave need processing
description: How replenishment quantities are calculated when demand exceeds available stock.
product: widget
related: [widget/wave-planning, widget/replenishment-triggers]
sources: ["Operations Guide 2024, section 8.3"]
---

## Overview

Replenishment is triggered when on-hand quantity in a pick location falls below its minimum...
```

Small, self-contained, cross-linked, and carrying its own provenance. The
[cards reference](cards.md) covers every field and all five types.

## Where to go next

- [Architecture](architecture.md) for how the three stages fit together.
- [Principles](principles.md) for the decisions that constrain the design.
- [Getting started](../guides/getting-started.md) to see it working.

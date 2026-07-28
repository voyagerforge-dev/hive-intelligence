# Hive documentation

Four layers, in the order most people need them.

## Concepts

Read these to understand what Hive is and why it is shaped the way it is.

| | |
|---|---|
| [Overview](concepts/overview.md) | the problem, the approach, and who this is for |
| [Cards](concepts/cards.md) | the OKF card format: five types, frontmatter, facets, ids |
| [Architecture](concepts/architecture.md) | three stages, two doors, two stores |
| [Principles](concepts/principles.md) | the decisions that constrain everything else |

## Guides

Task-shaped. Each one is something you actually want to do.

| | |
|---|---|
| [Getting started](guides/getting-started.md) | serve the fixture corpus and query it |
| [Building a corpus](guides/building-a-corpus.md) | documents to cards, through three human gates |
| [Serving cards](guides/serving-cards.md) | running `hive-serve`, identity, client isolation |
| [Corrections and memory](guides/corrections-and-memory.md) | keeping a corpus true over time |
| [Database objects](guides/database-objects.md) | schema to cards without a model |
| [Issue journal](guides/issue-journal.md) | support tickets to client-scoped issue cards |

## Reference

Look things up here.

| | |
|---|---|
| [Configuration](reference/configuration.md) | every setting, per package, with defaults |
| [Metrics](reference/metrics.md) | everything on `/metrics`, and what to alert on |
| [hive-prep](reference/hive-prep.md) · [hive-gen](reference/hive-gen.md) · [hive-serve](reference/hive-serve.md) | the pipeline |
| [hive-author](reference/hive-author.md) · [hive-dbparse](reference/hive-dbparse.md) · [hive-zendesk](reference/hive-zendesk.md) | the extensions |

## Architecture decisions

| | |
|---|---|
| [Product and deployment boundary](architecture/product-deployment-boundary.md) | what belongs in this repository, and what does not |

---

## What belongs here, and what does not

This repository documents **the product**. Documentation about applying Hive to a particular
domain belongs with that deployment.

The dividing line is the one that governs the code: documentation of a **mechanism** is here,
documentation of an **application** of that mechanism is not. The card pipeline, the facet model
and the resolver are mechanisms. Distilling one vendor's product manuals, or the runbook for one
organisation's servers, is an application.

So you will not find a host name, an IP address, a client name or a deploy procedure anywhere in
these pages. If you find one, it is a bug worth reporting.

## A note on names

**OKF** is the card format: a small specification of what a card file looks like, covering the
frontmatter keys, the five types, and the `okf_version` field. Cards written by Hive are readable
by anything that understands OKF, and Hive can serve OKF cards it did not produce.

**Hive** is the system that produces and serves them.

The distinction is practical. Anything below that says *OKF* describes the file format and is a
statement about data. Anything that says *Hive* describes software. Where `okf_` prefixes survive
in configuration keys and metric names they predate the split and are kept deliberately, because
renaming them breaks running deployments and existing dashboards; the
[configuration reference](reference/configuration.md) flags each one.

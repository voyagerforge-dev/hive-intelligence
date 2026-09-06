# Hive Intelligence

[![CI](https://github.com/voyagerforge-dev/hive-intelligence/actions/workflows/fastapi-svcs.yml/badge.svg?branch=main&event=push)](https://github.com/voyagerforge-dev/hive-intelligence/actions/workflows/fastapi-svcs.yml?query=branch%3Amain+event%3Apush)
[![Licence: Apache 2.0](https://img.shields.io/badge/licence-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://pypi.org/project/vf-hive-serve/)
[![vf-hive-serve](https://img.shields.io/pypi/v/vf-hive-serve.svg?label=vf-hive-serve)](https://pypi.org/project/vf-hive-serve/)
[![vf-hive-gen](https://img.shields.io/pypi/v/vf-hive-gen.svg?label=vf-hive-gen)](https://pypi.org/project/vf-hive-gen/)
[![vf-hive-prep](https://img.shields.io/pypi/v/vf-hive-prep.svg?label=vf-hive-prep)](https://pypi.org/project/vf-hive-prep/)

Curated knowledge, served to an AI agent as cards rather than retrieved as chunks.

Hive turns a body of documentation into a reviewed, cross-linked set of small markdown files in
git, then serves those files to any MCP or REST client over those two doors. There is no vector
index, no embedding model, and no model call at serving time. The agent is the reasoning loop; Hive
decides what it is allowed to reason over.

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

Six Python packages under `tooling/`. Three form the pipeline; three extend it. Five are published
to PyPI as one engine at one version.

| Package | Install | Does |
|---|---|---|
| `hive-prep` | `pip install vf-hive-prep` | raw documents to clean atomic markdown |
| `hive-gen` | `pip install vf-hive-gen` | atomic markdown to reviewed concept cards, and the card model |
| `hive-serve` | `pip install vf-hive-serve` | serves cards over REST and MCP, with a per-person work ledger |
| `hive-dbparse` | `pip install vf-hive-dbparse` | database schema to cards, deterministically, with no model involved |
| `hive-zendesk` | `pip install vf-hive-zendesk` | closed support tickets to client-scoped issue cards |
| `hive-author` | from source, `tooling/hive-author` | a write-only door for filing corrections and memory, so `hive-serve` holds no credentials |

`hive-author` is **not published to PyPI**. It is versioned separately from the other five and is
deployed as a service rather than installed as a library; see
[distributing the engine](docs/architecture/engine-distribution.md).

`vf-hive-serve` pins `vf-hive-gen` exactly, so installing it brings the matching card model.

## Start here

You need **Python 3.12 or later** and [uv](https://docs.astral.sh/uv/). No credentials of your own
and no corpus of your own.

```bash
git clone https://github.com/voyagerforge-dev/hive-intelligence.git
cd hive-intelligence/tooling/hive-serve
uv sync --extra dev
```

**[Getting started](docs/guides/getting-started.md)** takes it from there and has `hive-serve`
answering questions from the bundled fixture corpus in about five minutes. It needs docker or
podman for one throwaway Postgres, because the work ledger is a database and `hive-serve` refuses to
start without one.

Then:

- **[Documentation](docs/README.md)** is the map.
- **[Overview](docs/concepts/overview.md)** is the problem this solves and who it suits, with no
  prior context assumed.
- **[Architecture](docs/concepts/architecture.md)** is the conceptual reference, and
  **[the pipeline end to end](docs/concepts/pipeline.md)** is the long form with diagrams.

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

**The skills under `skills/` do name a domain, deliberately.** The five agent skills are worked
examples written for the Manhattan WMOS/SCALE support practice Hive was first built for, and four
of the five say so in their `description:` line. What each one describes - how to ground an answer
in cards, work a diagnosis, plan a piece of work, teach a topic, file a correction - is general;
the nouns are not. They ship to be adapted to your own domain. Nothing in the card model or the
fixtures requires those nouns; [skills/README.md](skills/README.md) has the detail,
and [known limitations](docs/concepts/principles.md#known-limitations) lists the vocabulary still
baked into the tooling.

## Tests

Each package is independent. From any package directory:

```
uv sync --extra dev && uv run pytest -q
```

Assertions that depend on a live corpus, on its evaluation datasets, or on the GitHub
card-submission surface skip with a stated reason when their subject is absent. In this
repository they are expected to skip. In a deployment that has a corpus, they run.

`hive-serve`'s ledger tests are the exception: they start a real Postgres container and fail rather
than skip when they cannot, because a skipped ledger test reports green.

## Releases

The five published distributions ship as **one engine at one version**. Publication happens only
from a pushed `v*` tag, to PyPI, wheels only, over Trusted Publishing with no token stored anywhere.

There is no changelog file in this repository, deliberately. The release workflow is the record, so
what changed in a version lives where that version was actually cut:

- **[Releases](https://github.com/voyagerforge-dev/hive-intelligence/releases)** and
  **[tags](https://github.com/voyagerforge-dev/hive-intelligence/tags)** on GitHub. Every version is
  an annotated tag, and its message says what changed and what it breaks. `git show v0.6.0` reads
  the same thing offline.
- **PyPI** for what is installable: [vf-hive-prep](https://pypi.org/project/vf-hive-prep/),
  [vf-hive-gen](https://pypi.org/project/vf-hive-gen/),
  [vf-hive-serve](https://pypi.org/project/vf-hive-serve/),
  [vf-hive-dbparse](https://pypi.org/project/vf-hive-dbparse/),
  [vf-hive-zendesk](https://pypi.org/project/vf-hive-zendesk/). All five carry the same version.
- **[Distributing the engine](docs/architecture/engine-distribution.md)** is how a version is cut
  and what a consumer pins.

## Contributing

- [CONTRIBUTING.md](CONTRIBUTING.md) - how to get set up, what CI does to your pull request, and
  what a good one looks like here.
- [AGENTS.md](AGENTS.md) - the short, authoritative note on how this repository is built, tested
  and released, and on the sharp edges. Written for whoever is next in the code, human or
  otherwise.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) - Contributor Covenant 2.1.
- [SECURITY.md](SECURITY.md) - the private route for a vulnerability. Please do not use a public
  issue.

## Licence

[Apache License 2.0](LICENSE). Use it, run it, modify it, redistribute it, build a product on
it. The licence includes an express patent grant.

**The licence covers the software, not any corpus.** A corpus belongs to whoever produced it and
ships separately; see [NOTICE](NOTICE).

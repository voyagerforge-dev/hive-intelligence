# OKF tooling reference

*Module-level technical reference for the OKF Python tooling - what each script does, how it
works, and how it is deployed. The conceptual model (the pipeline, the two stores, the facets,
the design decisions) lives in [Architecture & Concepts](../OKF-Pipeline.md); this set is the
code-level companion to it.*

**Tooling reference:** **Hub** · [hive-prep](hive-prep.md) · [hive-gen](hive-gen.md) · [hive-serve](hive-serve.md) · [hive-dbparse](hive-dbparse.md) · [hive-author](hive-author.md) · [hive-zendesk](hive-zendesk.md) · [Architecture & Concepts](../OKF-Pipeline.md)

---

## The six packages

Everything lives under `knowledge/okf/tooling/<package>/`. Each is a self-contained, `uv`-managed
Python package with fakes-only tests.

| Package | Role | Pipeline stage / tier | Runs as | Doc |
|---|---|---|---|---|
| `hive-prep` | raw vendor docs → atomic markdown | [Stage 1](../OKF-Pipeline.md#3-stage-1-document-preparation-hive-prep) | dev-box CLI (`uv`), orchestrated by `/wms-prep` | [hive-prep.md](hive-prep.md) |
| `hive-gen` | atomic markdown → concept cards, plus post-promote + corrections/memory authoring | [Stage 2](../OKF-Pipeline.md#4-stage-2-card-creation-hivegen) | dev-box CLI (`uv`) + a Windmill gate | [hive-gen.md](hive-gen.md) |
| `hive-serve` | serve cards to Claude over REST + MCP, with a per-owner work ledger | [Stage 3](../OKF-Pipeline.md#5-stage-3-serving-hive-serve) | container on Host-A (`:8015`) | [hive-serve.md](hive-serve.md) |
| `hive-dbparse` | Manhattan deploy DDL → database-object cards | [db-object tier](../OKF-Pipeline.md#the-database-object-tier-hive-dbparse) | one-time dev-box parse | [hive-dbparse.md](hive-dbparse.md) |
| `hive-author` | file memory/correction issues, keeping hive-serve keyless | [authoring door](../OKF-Pipeline.md#the-memory-layer) | container on Host-A (`:8016`) | [hive-author.md](hive-author.md) |
| `hive-zendesk` | closed Zendesk tickets → client issue-journal entries | [issue-journal tier](hive-zendesk.md) | dev-box CLI (`uv`); monthly Windmill job pending | [hive-zendesk.md](hive-zendesk.md) |

## How to read this set

- Start from [Architecture & Concepts](../OKF-Pipeline.md) for the *why* and the data flow; come
  here for the *how* of any given module.
- Each package doc opens with a **module index** table, then one **per-module block** -
  *purpose · key logic · inputs → outputs · dependencies · invoked / deployed* - then a
  **deployment & runtime** section and a **tests** note.

## Cross-cutting conventions

- **Sovereign + LLM-free at serve time.** Only Stages 1-2 (`hive-prep`, `hive-gen`) call models, on
  the firm's Bifrost gateway (`VK_OKF`); `hive-serve` and `hive-dbparse` call no model at all.
- **git is the system of record.** Cards are plain markdown files; the only mutable store is
  `hive-serve`'s SQLite objective/memory ledger.
- **Fakes-only tests.** Every package tests without live models or network:
  `cd tooling/<package> && uv sync --extra dev && uv run pytest -q`.
- **Two servers stay keyless-vs-keyed by design.** `hive-serve` holds no credential (read-only);
  `hive-author` holds the single `issues:write` GitHub token, in its own container.

## See also

- [Architecture & Concepts](../OKF-Pipeline.md) - the pipeline, stores, facets, and design decisions.
- [OKF overview / documentation map](../../README.md).
- Operations: [Deploy hive-serve](../../tooling/hive-serve/deploy/README.md) and
  [the Cloudflare Access gate](../../../../infra-repo/docs/runbooks/okf-mcp-cf-access-oauth.md).

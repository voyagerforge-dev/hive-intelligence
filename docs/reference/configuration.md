# Configuration

Every package reads settings from the environment, or from a `.env` file beside it. Names below are
the environment variable names; each package's `config.py` is the authority.

Each package ships a `.env.example` listing the keys it actually needs.

## Names that mention a vendor

Several variables are named after the specific tools Hive was first built against rather than after
the role they fill:

| Variable | Actually means |
|---|---|
| `BIFROST_BASE`, `BIFROST_API_KEY` | any OpenAI-compatible model gateway |
| `DOCLING_BASE`, `DOCLING_API_KEY`, `PREFER_DOCLING` | the document converter service |
| `QWEN_BASE`, `QWEN_API_KEY`, `QWEN_MODEL` | the vision model endpoint |

None of these require the named product. Any OpenAI-compatible endpoint satisfies the first and
third; the second wants a converter speaking the same HTTP contract.

The names are kept for the same reason as the `OKF_` prefixes below: renaming an environment
variable does not fail loudly, it starts the service with a default instead. Renaming them is
tracked work and belongs with a major version, not a documentation pass.

The model defaults are likewise recommendations rather than requirements, and name models that must
exist on *your* gateway. Set them explicitly.

## A note on `OKF_` prefixes

Three settings still carry an `OKF_` prefix from before the format and the system had separate
names. They configure Hive, not the OKF format, so the prefix is now misleading.

They are kept anyway. Renaming an environment variable silently changes behaviour on every existing
deployment at the moment it is redeployed, and the failure is a service that starts cleanly with
default settings rather than an error. That is not a trade worth making for tidiness. They are
flagged where they appear.

## hive-serve

| Variable | Default | Notes |
|---|---|---|
| `CONCEPTS_DIR` | `../../concepts` | corpus concept cards. The default assumes a layout that will not be yours |
| `CLIENTS_DIR` | `../../clients` | client-scoped cards. Omit to disable client memory entirely |
| `EVAL_DIR` | empty | labelled eval sets, **evaluation only**. No default: they ship with a corpus |
| `LEDGER_DSN` | empty | **required**. Postgres for the objective and memory ledger. **The only state not in git** |
| `OKF_DATA_DIR` | `./.data` | non-ledger scratch, including `run_eval` reports |
| `HOST` | `127.0.0.1` | loopback by default, deliberately |
| `PORT` | `8000` | |
| `TRANSPORT` | `stdio` | `stdio` for direct MCP clients, or HTTP via `serve --http` |
| `IDENTITY_HEADER` | `x-forwarded-email` | the trusted header. **Trusted, not verified** |
| `OKF_DEFAULT_OWNER` | `local-operator` | ledger owner when no identity header is present |
| `MAX_CARDS` | `8` | bundle size cap for `/resolve` |
| `MAX_CHARS` | `40000` | bundle character cap |
| `RESOLVE_DEPTH` | `1` | how far to follow `related` |
| `BIFROST_BASE` | empty | model gateway, **evaluation only**. Serving makes no model calls |
| `BIFROST_API_KEY` | empty | as above |
| `SELECT_MODEL` | `deepseek-v4-flash` | evaluation harness only |
| `ANSWER_MODEL` | `minimax-m3` | evaluation harness only |
| `JUDGE_MODEL` | `minimax-m3` | evaluation harness only |
| `BIFROST_TIMEOUT_S` | `300` | |

`IDENTITY_HEADER` names a header that is trusted on arrival. There is no signature check. Anything
that can reach the port can claim any identity, which is why the default binding is loopback and
why an authenticating proxy is mandatory rather than advisable for any wider exposure. See
[serving cards](../guides/serving-cards.md#identity-and-what-it-is-not).

## hive-gen

| Variable | Default | Notes |
|---|---|---|
| `CARD_CORPUS_ROOT` | empty | **required**. The card corpus working tree: taxonomies, `drafts/`, `.pipeline/`. Not hive-prep's `CORPUS_ROOT` |
| `ATOMIC_DIR` | empty | atomic markdown from `hive-prep` |
| `SLICE_AREA` | empty | which functional area to generate |
| `BIFROST_BASE` | required | model gateway |
| `BIFROST_API_KEY` | required | |
| `TAXONOMY_MODEL` | `minimax-m3` | gate 2, the concept list |
| `ASSIGN_MODEL` | `deepseek-v4-flash` | document to concept assignment |
| `DISTILL_MODEL` | `minimax-m3` | gate 3, the card bodies |
| `MAX_CHARS` | `24000` | source characters per distillation call |
| `BIFROST_TIMEOUT_S` | `300` | |
| `CARD_BASE_URL` | `https://hive.example.com/card` | used by `conformance_pass` for the `resource` field |

The functional-area map (`AREAS`, `SUBAREAS` in `hivegen/load.py`) and the guide-topic vocabulary
(`hivegen/retopic.py`) are **source code, not configuration**, and describe the corpus Hive was
first built against. See [known limitations](../concepts/principles.md#known-limitations).

## hive-prep

| Variable | Default | Notes |
|---|---|---|
| `CORPUS_ROOT` | empty | the raw document tree to ingest. Not hive-gen's `CARD_CORPUS_ROOT` |
| `WORK_DIR` | `./hive-work` | scratch space |
| `ATOMIC_DIR` | `./hive-work/atomic` | output, and `hive-gen`'s input |
| `DOCLING_BASE` | empty | document converter endpoint |
| `DOCLING_API_KEY` | empty | |
| `DOCLING_TIMEOUT_S` | `300` | |
| `DOCLING_CA_BUNDLE` | empty | for a converter behind a private CA |
| `PREFER_DOCLING` | `true` | falls back to local conversion when unavailable |
| `QWEN_BASE` | empty | vision model, for pages with no extractable text |
| `QWEN_API_KEY` | empty | |
| `QWEN_MODEL` | `qwen3.8-27b` | |
| `QWEN_TIMEOUT_S` | `600` | |
| `VISION_MIN_CHARS` | `100` | below this, a page is treated as needing vision |
| `LO_JOBS` | `8` | local converter concurrency |
| `STRIP_BOILERPLATE` | `true` | |
| `STRIP_PRODUCT` | `default` | which rule set in `stripper_rules/`. Vendor sets are opt-in and corpus-side |

## hive-author

| Variable | Default | Notes |
|---|---|---|
| `GITHUB_TOKEN` | empty | **required**. Scope it to issue creation on one repository |
| `GITHUB_REPO` | empty | **required**. No default: a wrong-but-plausible one files issues into someone else's repository |
| `GITHUB_API` | `https://api.github.com` | change for GitHub Enterprise |
| `HOST` | `127.0.0.1` | |
| `PORT` | `8000` | |
| `IDENTITY_HEADER` | `cf-access-authenticated-user-email` | same trust model as `hive-serve` |
| `OKF_DEFAULT_OWNER` | `local-operator` | |

This is the only service that holds a credential. Keep the token narrow: it needs to open issues on
the corpus repository and nothing else.

## hive-zendesk

| Variable | Default | Notes |
|---|---|---|
| `CONNECTOR_BASE` | empty | **required**. Validated at startup rather than on first request |
| `CONNECTOR_API_KEY` | empty | |
| `BIFROST_BASE` | empty | model gateway |
| `BIFROST_API_KEY` | empty | |
| `DISTILL_MODEL` | `minimax-m3` | |
| `RERANK_MODEL` | `minimax-m3` | linking is measured separately from distilling |
| `DISTILL_MAX_TOKENS` | `4000` | must cover reasoning **and** the answer for a reasoning model. At 2000 it spends the budget thinking and returns nothing |
| `BIFROST_TIMEOUT_S` | `300` | |
| `CONNECTOR_PAGE_CAP` | `3000` | the source's own ceiling |
| `CAP_WARN_RATIO` | `0.95` | warn near the cap: a truncated pull looks like a complete one |
| `RESHAPE_WORKERS` | `6` | `rebuild` concurrency |
| `RESHAPE_BATCH_SIZE` | `5` | cards per model call in `rebuild` |

## hive-dbparse

No environment configuration. Everything is command-line: `--src`, `--out`, `--limit-modules`.

## Settings that have no default on purpose

`CONNECTOR_BASE`, `GITHUB_REPO`, `LEDGER_DSN` and the gateway addresses are empty by default and
validated at startup.

A default that points somewhere plausible does not save you configuration. It moves the failure from
startup, where it is obvious, to first use, where it appears as a connection error against a host
you have never heard of. Empty and validated is louder and cheaper.

## Where the corpus is

`CORPUS_ROOT`, `CARD_CORPUS_ROOT`, `CONCEPTS_DIR`, `CLIENTS_DIR` and `EVAL_DIR` all name parts of
the **corpus**, which has been a separate repository from the engine since 2026-08-11. Nothing about where it sits on disk
follows from where this code is installed, so every one of them is configuration and none of them is
derived.

They were derived once, by walking up the directory tree from the source file. That arithmetic used
to land inside the same tree and now lands in the engine repository, which contains no cards, no
taxonomies and no eval sets. It failed silently in every case: a glob over a directory that is not
there yields nothing and raises nothing, so `hive-gen` re-proposed a taxonomy it already had and
`run_eval` scored an absent corpus zero and printed the result.

So the tools that read the corpus check first and refuse with a message naming the setting, rather
than proceeding over nothing. The check is "set, and a directory", never "looks like a corpus": a
corpus that has not been generated yet legitimately holds almost nothing.

Directory arithmetic from `__file__` is still correct for a package finding its **own** files. It is
never correct for finding another repository's.

`CORPUS_ROOT` and `CARD_CORPUS_ROOT` are two different trees and are deliberately named apart.
`CORPUS_ROOT` is hive-prep's input, the raw documents going **in**; `CARD_CORPUS_ROOT` is hive-gen's
output, the card corpus coming **out** and the tree hive-serve then serves. A single name would have
been read by both, and the process environment outranks a per-package `.env`, so an operator running
the [build guide](../guides/building-a-corpus.md) stages back to back would have exported one value
for both. The check here is "set, and a directory" by design, so the raw document tree would have
passed hive-gen's guard and the taxonomy lookup would have gone missing all over again.

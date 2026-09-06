# Configuration

Packages that have settings read them from the environment, or from a `.env` file beside them, and
ship a `.env.example` listing the keys they actually need. Names below are the environment variable
names; the package's `config.py` is the authority. `hive-dbparse` has no settings at all - see
[below](#hive-dbparse).

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
exist on *your* gateway, under the id that gateway uses: OpenRouter, the address the `.env.example`
files sample, namespaces ids by provider (`deepseek/deepseek-v4-flash`). Set them explicitly -
against a reachable gateway a wrong id comes back as an unknown model, so the error names the model
rather than the setting.

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
| `CONCEPTS_DIR` | `../../concepts` | **required in practice**. Corpus concept cards; the server refuses to start unless it names a directory. The default is relative and will not be yours - read the warning below before relying on the refusal |
| `CLIENTS_DIR` | `../../clients` | client-scoped cards. Leave empty to disable client memory entirely; never a startup refusal |
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
| `SELECT_MODEL` | `deepseek/deepseek-v4-flash` | evaluation harness only. Provider id, not a gateway alias |
| `ANSWER_MODEL` | `deepseek/deepseek-v4-pro` | evaluation harness only |
| `JUDGE_MODEL` | `deepseek/deepseek-v4-pro` | evaluation harness only |
| `BIFROST_TIMEOUT_S` | `300` | |

For `IDENTITY_HEADER`'s ledger-owner role and the mandatory proxy for wider exposure, see
[the serving trust boundary](../guides/serving-cards.md#identity-and-what-it-is-not).

### `CONCEPTS_DIR`'s default is relative, and that is a trap

> **Set `CONCEPTS_DIR` explicitly, to an absolute path.** Its default, `../../concepts`, is
> resolved against the **working directory of the process**, not against where `hive-serve` is
> installed. Two identically configured deployments started from two different directories
> therefore serve two different corpora, or one corpus and one refusal, with nothing in the logs
> to distinguish them.

The startup check is "set, and a directory" - it is not "is this the corpus you meant". It catches
an unset value and a path that does not exist. It cannot catch `../../concepts` happening to
resolve onto *something*: a stale corpus, a half-synced clone, another deployment's tree. That
serves a wrong answer confidently, which is the one failure mode this system exists to avoid, and
it is worse than the refusal you would have got from an empty setting.

The default is kept because removing it is a breaking change for every deployment that currently
relies on it, which belongs with a major version rather than a documentation pass. Making it refuse
outright, the way `LEDGER_DSN` does, is the fix; it is not this document's to make.

The same reasoning applies to `CLIENTS_DIR`'s `../../clients`, with one difference: `CLIENTS_DIR`
is legitimately optional, so an empty value means *off* rather than *the working directory*, and it
is never a startup refusal. A wrong-but-existing relative path is the same trap there, and it
silently serves another deployment's client memory.

## hive-gen

| Variable | Default | Notes |
|---|---|---|
| `CARD_CORPUS_ROOT` | empty | **required**. The card corpus working tree: taxonomies, `drafts/`, `.pipeline/`. Not hive-prep's `CORPUS_ROOT` |
| `ATOMIC_DIR` | empty | atomic markdown from `hive-prep`. Optional - empty falls back to R2 - but validated when set, and a run that loads no documents refuses |
| `SLICE_AREA` | empty | which functional area to generate |
| `R2_ENDPOINT` | empty | **required when the R2 fallback is used**. No default, and an empty one is not usable: botocore raises `ValueError: Invalid endpoint:` as the client is built, several frames down, naming no setting |
| `R2_ACCESS_KEY_ID` | empty | |
| `R2_SECRET_ACCESS_KEY` | empty | |
| `R2_BUCKET` | empty | **required when the R2 fallback is used**. No default: a bucket that is not yours lists nothing, which reads exactly like a bucket with nothing in it |
| `R2_PREFIX` | empty | **required when the R2 fallback is used**. A bucket holds more than one dataset, so an empty prefix is not "everything I wanted", it is "everything anyone put there" |
| `BIFROST_BASE` | required | model gateway |
| `BIFROST_API_KEY` | required | |
| `TAXONOMY_MODEL` | `minimax/minimax-m3` | gate 2, the concept list |
| `ASSIGN_MODEL` | `deepseek/deepseek-v4-flash` | document to concept assignment |
| `DISTILL_MODEL` | `minimax/minimax-m3` | gate 3, the card bodies |
| `MAX_CHARS` | `24000` | source characters per distillation call |
| `BIFROST_TIMEOUT_S` | `300` | |
| `CORPUS_PROFILE` | empty | path to the corpus profile, the domain vocabulary that ships with a corpus. Empty means look for `corpus-profile.yaml` in the working directory, then beside `ATOMIC_DIR` |
| `CARD_BASE_URL` | `/card` | the base a card id resolves under, in the `resource` field. Read by both card-writing commands, `hivegen-conformance-pass` (concept cards) and `hivegen-memory-from-issue` (client memory cards). **A path, not a host, and deliberately so** - see below. Read from the environment by the scripts, not through `config.py` |

**`CARD_BASE_URL` defaults to a path because a card outlives a hostname.** One corpus wrote 991
cards with an absolute URI and had to rewrite every one of them when its deployment moved domains.
Set it only where a deployment genuinely needs absolute URIs, and expect to rewrite them the next
time it moves.

The functional-area map (`AREAS`, `SUBAREAS` in `hivegen/load.py`) and the guide-topic vocabulary
(`hivegen/retopic.py`) are **source code, not configuration**, and describe the corpus Hive was
first built against. See [known limitations](../concepts/principles.md#known-limitations).

## hive-prep

| Variable | Default | Notes |
|---|---|---|
| `CORPUS_ROOT` | empty | corpus-profile lookup hint only, and read from the environment, so it must be **exported**. The raw tree comes from the curation plan or the command argument. Not hive-gen's `CARD_CORPUS_ROOT` |
| `CORPUS_PROFILE` | empty | the same profile file [hive-gen reads](#hive-gen), for the folder-name product aliases and the vocabulary `validate-plan` checks a plan against. Read from the environment, so it must be **exported**. Empty means look for `corpus-profile.yaml` in the working directory, then under `CORPUS_ROOT` and beside it |
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
| `FORGE_KIND` | empty | **required**. `github` or `forgejo`. No default and never inferred from `FORGE_API`: the two APIs disagree on the `labels` field, so guessing wrong fails the submission rather than the startup |
| `FORGE_API` | empty | **required**. The forge's API base, deployment-specific. No default, deliberately not a public one: a default pointing anywhere reachable lets a misconfigured deployment file submissions somewhere real |
| `FORGE_REPO` | empty | **required**. The corpus repository submissions are filed against. No default: a wrong-but-plausible one files issues into someone else's repository |
| `FORGE_TOKEN` | empty | the credential. Scope it to opening issues on that one repository. Set this **or** `FORGE_TOKEN_FILE`, never both |
| `FORGE_TOKEN_FILE` | empty | a file holding the credential, re-read on every submission. For a token that expires faster than this process lives, such as a GitHub App installation token at one hour |
| `HOST` | `127.0.0.1` | |
| `PORT` | `8000` | |
| `IDENTITY_HEADER` | `cf-access-authenticated-user-email` | same trust model as `hive-serve`: trusted, not verified |
| `OKF_DEFAULT_OWNER` | `local-operator` | |

`FORGE_KIND`, `FORGE_API`, `FORGE_REPO` and a credential are all checked at startup, and the
service refuses to start naming what is missing.

This is the only service that holds a credential. Keep it narrow: it needs to open issues on the
corpus repository and nothing else. It cannot push, merge, or open a pull request, and that is the
point of it being a separate service from `hive-serve`.

## hive-zendesk

| Variable | Default | Notes |
|---|---|---|
| `CONNECTOR_BASE` | empty | **required**. Validated at startup rather than on first request |
| `CORPUS_PROFILE` | empty | the same profile file [hive-gen reads](#hive-gen), for its `linking` section: the default product, the per-product markers, and the extra stopwords. Read from the environment, so it must be **exported**. Empty means look for `corpus-profile.yaml` in the working directory |
| `CONNECTOR_API_KEY` | empty | |
| `BIFROST_BASE` | empty | model gateway |
| `BIFROST_API_KEY` | empty | |
| `DISTILL_MODEL` | empty | **required**, refused at startup unless `--model` is passed. No default on purpose: an environment that fails to load `.env` would otherwise distil a whole run with an unintended model, silently, and the cards carry no record of which one wrote them |
| `RERANK_MODEL` | `minimax/minimax-m3` | linking is measured separately from distilling |
| `DISTILL_MAX_TOKENS` | `4000` | must cover reasoning **and** the answer for a reasoning model. At 2000 it spends the budget thinking and returns nothing |
| `BIFROST_TIMEOUT_S` | `300` | |
| `CONNECTOR_PAGE_CAP` | `3000` | the source's own ceiling |
| `CAP_WARN_RATIO` | `0.95` | warn near the cap: a truncated pull looks like a complete one |
| `RESHAPE_WORKERS` | `6` | `rebuild` concurrency |
| `RESHAPE_BATCH_SIZE` | `5` | cards per model call in `rebuild` |
| `R2_ENDPOINT` | empty | **required by `rebuild`**, refused at startup. No default, and an empty one is not usable: botocore raises `ValueError: Invalid endpoint:` as the client is built, several frames down, naming no setting |
| `R2_ACCESS_KEY_ID` | empty | |
| `R2_SECRET_ACCESS_KEY` | empty | |
| `R2_BUCKET` | empty | **required by `rebuild`**, refused at startup. No default: a bucket that is not yours lists nothing, which reads exactly like a bucket with nothing staged in it |

## hive-dbparse

No environment configuration, and no `config.py` or `.env.example`. Everything is command-line: see
[the option table](hive-dbparse.md#running).

## Settings that have no default on purpose

`CONNECTOR_BASE`, `FORGE_API`, `FORGE_REPO`, `FORGE_KIND`, `LEDGER_DSN`, `EVAL_DIR`,
`CARD_CORPUS_ROOT`, `R2_ENDPOINT`,
`R2_BUCKET`, `R2_PREFIX`, hive-zendesk's `DISTILL_MODEL` and the gateway addresses are empty by
default and validated at startup or at the point of use.

`CONCEPTS_DIR` and `CLIENTS_DIR` are the two that did not join that list, and they are the
weakest link in it: both carry a **relative** default that a working directory can make real. See
[the warning above](#concepts_dirs-default-is-relative-and-that-is-a-trap).

A default that points somewhere plausible does not save you configuration. It moves the failure from
startup, where it is obvious, to first use, where it appears as a connection error against a host
you have never heard of. Empty and validated is louder and cheaper.

The R2 settings joined that list on 2026-09-03, from the audit of what the published wheels would
contain. `R2_BUCKET` in hive-zendesk and `R2_PREFIX` in hive-gen named a real private bucket and a
real prefix inside it, which was a disclosure to everyone who installed the package as well as the
usual silent fallback. Object storage makes the silent version worse than a filesystem does: a
listing against a bucket you cannot see returns an empty list, not an error. `R2_ENDPOINT` was
already empty but unchecked, and it is refused alongside them for the other half of the rule: an
empty `endpoint_url` reaches botocore and raises `ValueError: Invalid endpoint:` as the client is
built, which is loud but names no setting, so the operator is told a URL is malformed rather than
which of theirs is unset. It never reaches AWS - botocore falls back to an AWS endpoint only when
`endpoint_url` is `None`, and these settings are strings that default to empty.

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

Unset counts as wrong, and is the easier one to miss. `Path("")` is `Path(".")`, which exists, so an
empty setting that reaches `pathlib` resolves to the working directory rather than failing - an
empty `CONCEPTS_DIR` used to build the served catalogue out of whatever markdown happened to sit
beside the process. So `hiveserve serve` refuses at startup, alongside its `LEDGER_DSN` refusal, and
an empty answer is never allowed to become a wrong one.

`CLIENTS_DIR` is the deliberate exception, because omitting it disables client memory and that is a
supported deployment. It is never a startup refusal. Empty is coerced to "off" once, in
`hiveserve/resolver.py`, so every door agrees; `run_eval` refuses only when the eval set it was
handed actually has rows that exercise client memory, and otherwise reports a dead path rather than
degrading quietly - but only when some source actually set `CLIENTS_DIR`, since naming a default
nobody chose would warn on every run of a deployment that has no client memory. See
[hive-serve](hive-serve.md#the-evaluation-harness) for what the eval does with it.

An emptiness check counts what the consumer counts. `run_eval` asks `load_index` rather than
counting `*.md`, because `index.md`, `log.md` and the `<product>/db/` tier are not cards: a corpus
holding only those passes a file count and still scores zero on every question.

Directory arithmetic from `__file__` is still correct for a package finding its **own** files. It is
never correct for finding another repository's.

`CORPUS_ROOT` and `CARD_CORPUS_ROOT` are two different trees and are deliberately named apart.
`CORPUS_ROOT` is hive-prep's input, the raw documents going **in**; `CARD_CORPUS_ROOT` is hive-gen's
output, the card corpus coming **out** and the tree hive-serve then serves. A single name would have
been read by both, and the process environment outranks a per-package `.env`, so an operator running
the [build guide](../guides/building-a-corpus.md) stages back to back would have exported one value
for both. The check here is "set, and a directory" by design, so the raw document tree would have
passed hive-gen's guard and the taxonomy lookup would have gone missing all over again.

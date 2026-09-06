# Principles

Six decisions that constrain everything else. Each cost something, and the cost is stated.

## Git is the system of record

Cards are markdown files in a git repository. There is no database of record, no admin UI, and no
export step.

Review is a pull request. History is `git log`. Rollback is `git revert`. Access control is
repository permissions. All of it already exists, is already understood, and already has tooling.

**The cost.** No row-level querying, no transactions across cards, and merge conflicts on
concurrent edits. Acceptable, because a curated corpus changes on the order of tens of cards a day
by a handful of people, not thousands by hundreds.

## The model proposes, a person disposes, git records

Every model stage writes a reviewable artifact and stops. Nothing reaches the corpus without a
human action.

Three gates: the curation plan in stage 1, the taxonomy in stage 2, and the drafts before
promotion. Each is a file a person edits, not a dialog they click through.

**The cost.** It is slower, and it needs someone who cares about correctness. This is the whole
premise, though: if nobody will review, ordinary retrieval is cheaper and Hive buys you nothing.

## No model at serving time

The serving layer calls no model. See [architecture](architecture.md#no-model-at-serving-time).

**The cost.** Retrieval is keyword and id based, not semantic. A question phrased in words no card
uses may find nothing. That is a real limitation, and the intended response is to fix the card's
description rather than add a semantic ranker: if a concept cannot be found by the words people use
for it, its description is wrong, and a semantic index would have hidden that.

## Two clean stores

Knowledge and work state never mix. See [architecture](architecture.md#two-stores).

**The cost.** Promoting a personal note into shared knowledge is deliberate work rather than a
setting. That friction is the feature.

## Failures are loud

The system prefers stopping to continuing partially.

`hive-dbparse` fails the entire run on one unparsed construct rather than emitting a corpus that is
quietly missing objects. `hive-zendesk` warns when a source truncates its result set instead of
treating a short page as the end. Configuration that names an address has no default, because a
plausible-looking default fails later and against the wrong host.

The one place this rule is not yet honoured is `/healthz`, which reports healthy on an empty
corpus. That is a known wart, mitigated by alerting on the card count rather than on health, and it
has already cost one outage.

**The cost.** A pipeline that stops needs someone to unblock it. Cheaper than a corpus with holes
nobody can see.

## Product and deployment are separate

No deployment's host, address, mount path, scheduler or corpus appears in this repository. A
deployment is a fork of the product plus a corpus plus its own infrastructure configuration.

This is enforced rather than encouraged, and it is the reason several defaults are empty where a
convenient value would fit. See
[the boundary](../architecture/product-deployment-boundary.md).

**The cost.** More configuration to supply on a first deployment. In exchange, the product is
genuinely runnable by someone who has never seen the estate it was built in.

---

## Known limitations

Stated here rather than discovered later.

**Several settings are named after products rather than roles.** `BIFROST_*` means any
OpenAI-compatible gateway, `DOCLING_*` means the document converter, `QWEN_*` means the vision
endpoint. None requires the named product. Renaming them is a breaking change for every existing
deployment, so it belongs with a major version. See
[configuration](../reference/configuration.md#names-that-mention-a-vendor).

**Retrieval is lexical.** Covered above. Fix descriptions first: no lexical scorer can match a word
no card uses. If you need semantic search over the same content, embed the cards and keep your own
index: see [alongside an existing RAG system](../guides/alongside-rag.md).

**`product` is corpus-specific vocabulary hive-prep cannot infer, and a corpus built on the old
`WMS` default must be migrated by hand.** A curation-plan include with no `product` used to fall
back to the literal string `WMS`, the domain Hive was first built for, in `hiveprep/slugs.py` and
`hiveprep/transform.py`; it is refused now, because the product is the first segment of every slug
and that default filed the document under a product the corpus may not contain. The cost falls on
anyone who built a corpus while the default was live: this is a breaking change, and `hiveprep
route`, `transform` and `stamp` all refuse such a plan, naming the first offending entry, before
doing any work, so it will not run at all until every include carries a `product`.
Reproducing the slugs, R2 keys and stamped frontmatter that corpus already has means setting
`product: WMS` explicitly on those entries. Choosing a more accurate name instead is legitimate, but
it re-slugs those documents, which orphans the existing atomic docs and R2 keys rather than updating
them. This repository has no CHANGELOG, so this paragraph is the only place that note lives. On a
new corpus the burden is only that `product` must be stated: `validate-plan` reports every
product-less entry at gate 1 and lists the products your corpus profile declares, and `route`,
`transform` and `stamp` each refuse a plan that reaches them with one anyway, naming the entry and
pointing back at `validate-plan`. Related: the functional-area map and guide-topic vocabulary above.

**The OPS/traditional either-or is baked into the engine, not just the corpus.** `hive-gen`'s
regime classifier hardcodes `_LABELS = {"traditional", "ops", "none"}` and a system prompt defining
OPS (Order Planning Strategy / DC Order Planning) against standalone replenishment, tasking and
wave/fulfilment, in `hivegen/classify_regime.py`, and the scripts paired with it,
`scripts/regime_classify.py` and `scripts/regime_apply.py`, hardcode the same literals again, the
latter gating whether the facet is stamped at all; `hive-serve` restates the same either-or in the
eval harness's card-selection prompt in `hiveserve/agent.py`, telling the model the two are
mutually exclusive by site configuration. The facet itself is neutral: the resolver, the index and
the metrics only ever compare one card's `regime` against another's, never against a known label.
It is the hardcoded `ops` and `traditional` literals that are domain-bound, so a deployment in
another domain cannot use `regime` for its own within-product either-or without editing engine
source. Editing only the classifier and the prompts fails silently: the documented
classify/apply pair writes every card back with no `regime` facet and still reports
`stamped N cards. cross-regime related edges remaining: 0`. Grep the tree for those literals
rather than trust the list above. Making all of it corpus configuration rather than code is open
work. Related: the `hive-prep` product fallback above.

**The skills carry the same vocabulary, and are the first thing an outside reader meets.** The
`description:` lines in four of the five skills name one vendor's products, and `contribute/` names
them in its body and enumerates one corpus's facet values as if they were the product's. The
procedures are general; the nouns are not. This is the largest single-vendor surface left, and
generalising it is open work. See
[skills/README.md](../../skills/README.md).

**Client isolation is enforced at serving, not at rest.** Memory and issue cards for every client
sit in one repository, separated by directory and by resolver logic. Whoever can read the
repository can read all of it. If clients need cryptographic separation, they need separate
corpora.

**The ledger is the only state not in git.** A Postgres database holding objectives and personal
memory; see [the ledger](../reference/hive-serve.md#the-ledger). Back it up, because nothing else
will bring it back.

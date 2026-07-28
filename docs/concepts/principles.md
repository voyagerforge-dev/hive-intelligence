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
description rather than add a ranker: if a concept cannot be found by the words people use for it,
its description is wrong, and a semantic index would have hidden that.

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

No host, address, mount path, scheduler or corpus appears in this repository. A deployment is a
fork of the product plus a corpus plus its own infrastructure configuration.

This is enforced rather than encouraged, and it is the reason several defaults are empty where a
convenient value would fit. See
[the boundary](../architecture/product-deployment-boundary.md).

**The cost.** More configuration to supply on a first deployment. In exchange, the product is
genuinely runnable by someone who has never seen the estate it was built in.

---

## Known limitations

Stated here rather than discovered later.

**Vendor coupling remains in three places.** `hive-gen`'s functional-area map, its guide-topic
vocabulary, and `hive-dbparse`'s card id prefix are still specific to the corpus Hive was first
built against. They work, and they are configurable only by editing source. Making them
configuration is tracked work.

**Several settings are named after products rather than roles.** `BIFROST_*` means any
OpenAI-compatible gateway, `DOCLING_*` means the document converter, `QWEN_*` means the vision
endpoint. None requires the named product. Renaming them is a breaking change for every existing
deployment, so it belongs with a major version. See
[configuration](../reference/configuration.md#names-that-mention-a-vendor).

**Retrieval is lexical.** Covered above. Fix descriptions, not the ranker.

**Client isolation is enforced at serving, not at rest.** Memory and issue cards for every client
sit in one repository, separated by directory and by resolver logic. Whoever can read the
repository can read all of it. If clients need cryptographic separation, they need separate
corpora.

**The ledger is the only state not in git.** A SQLite file holding objectives and personal memory.
Back it up, because nothing else will bring it back.

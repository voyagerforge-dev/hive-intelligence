# Corrections and memory

A corpus is wrong the moment it is finished. Products change, decisions get made in meetings nobody
minuted, and a client turns out to do something the general documentation never mentioned.

Hive has two mechanisms for this, and they solve different problems.

|  | Corrections | Memory |
|---|---|---|
| Fixes | a shared card that is now wrong | knowledge that was never written down |
| Scope | everyone | one client, or one person |
| Lives in | `concepts/<product>/corrections/` | `clients/<client>/memory/` |
| Reaches the corpus by | review | review |

## Corrections

A correction is a card that overlays another card without editing it.

```yaml
---
type: correction
title: Calibration tolerance is 0.25 units, not 0.5
description: The calibration card states 0.5 units. The current bench standard is 0.25.
corrects: widget/calibration-routine
status: approved
---
```

When the resolver returns `widget/calibration-routine`, it attaches this correction alongside. The
agent sees the original statement and the amendment together.

### Why not just edit the card

Editing looks simpler and is worse, for three reasons.

**You lose the disagreement.** A correction records that someone believed one thing, then someone
else established another. That is often the most useful information in the corpus, because the next
person to hit the question will hit it the same way.

**You lose the trigger.** Corrections cluster. Five against one card means that card needs
rewriting, and the pattern is only visible if corrections are objects rather than diffs.

**You lose the low bar.** Editing a canonical card feels like it needs authority. Filing a
correction does not, so people actually do it. A correction anyone can propose and one reviewer can
approve gets filed; an edit that feels like it needs ownership does not.

### `status: approved` or nothing happens

**A correction is applied only when `status: approved`.**

A correction with no `status`, or `status: draft`, is inert. The file is in the tree, it looks
right, and it does nothing. The corpus continues serving the outdated claim.

This is the single easiest thing to get wrong. It is worth doing once deliberately, on the fixture
corpus, so you recognise the shape of it later: see
[getting started](getting-started.md#4-query-it).

## Memory

Memory is for what was never in a document. Most of it is client-specific deviation: the general
card is right, and this client does something else.

```yaml
---
type: memory
title: Alpha calibrates to 0.1 units
description: Alpha-specific. Alpha runs a tighter tolerance than the bench standard.
client: alpha
product: widget
related: [widget/calibration-routine]
submitted_by: someone@example.com
---
```

Two levels.

**Personal memory** lives in [the ledger](../reference/hive-serve.md#the-ledger), is private to
one person, and never enters the corpus. It is a working notebook: `remember`, `recall`, `forget`. No review, no ceremony, no
visibility to anyone else.

**Client memory** is a card in the corpus, visible to everyone who can read the corpus. The resolver
scopes it by client, so one client's cards never arrive in an answer scoped to another - but that is
retrieval scope, not access control: the client is an argument the caller chooses, and `get_card`
takes no client at all and returns any card by id. See
[the serving trust boundary](serving-cards.md#identity-and-what-it-is-not).

The path between them is deliberate and one-way.

## Promotion, and why `hive-serve` cannot write

When something in a personal notebook turns out to matter generally, the MCP `promote` tool
proposes it as a client memory card.

It does not write the card. It files a submission.

```
person  ──►  hive-serve  ──►  hive-author  ──►  issue on the corpus repo  ──►  PR  ──►  merge
             (no creds)       (issues:write)                                 review
```

`hive-serve` holds no credentials at all. This is the point: it is the component with the widest
exposure, so it holds nothing worth stealing and can write nothing. `hive-author` is a separate
service with a token scoped to opening issues on one repository and nothing else.

So a promotion becomes an issue, an issue becomes a pull request, and the corpus changes when a
person merges it. The same path a correction takes, and the same path a code change takes.

**The design consequence worth stating:** there is no way for an agent, or anyone using one, to put
a card into the corpus directly. Every card in a Hive corpus was merged by a human. That is what
makes the corpus worth trusting, and it is why the write path is a separate service rather than a
flag on the read one.

## Conflict checking

Memory submissions can contradict each other, or contradict a concept card. Catching that at review
is a judgement call, and reviewers under time pressure make it badly.

`hive-gen` ships the scoring machinery for an automated check that scores a submission against
existing cards and posts the result as a commit status, so a reviewer sees a flag rather than
having to go looking.

The scheduler that runs it is deployment-side. Hive ships the check, not the cron.

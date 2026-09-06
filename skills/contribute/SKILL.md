---
name: contribute
description: Use when the consultant wants to ADD a card to the knowledge base — capture a client-specific lesson, or fix a concept card that is wrong or out of date. Triggers like "add / contribute a card", "capture this for <client>", "remember this about <client>'s system", "this card is wrong / out of date", "correct <card>". Runs a short interview and files the card(s) through hive-author for review. NOT for answering questions — that is the base Hive skill.
---

You help a consultant contribute a card to Project-Hive. There are two kinds, and they go to two
different places — never blur them:

- **Memory** — how ONE client's system actually behaves (a site-specific modification or fact). It is
  client-scoped and can never touch core product knowledge.
- **Correction** — a core concept card is wrong or out of date. It amends the product knowledge itself
  and is never tied to a client.

You never write files, hold a token, or open a PR yourself. You file the card as an **issue** through
the keyless `hive-author` connector; a reviewer approves it and a GitHub Action opens and merges the PR.
Your job is to run a clean interview, sanitise, file, and tell the consultant what happens next.

## Playbook

1. **Decide the kind.** Infer from how they phrased it; ask only if genuinely ambiguous. Confirm in one
   line so they can correct you: *memory* = "how THIS client's system behaves"; *correction* = "the
   product card itself is wrong." If what they describe is really general product behaviour, it is a
   correction (or a new concept), not a memory.

2. **Run the matching branch below**, one point at a time — do not dump the whole form at once.

3. **File it**, then **ask whether to file another.** Loop for as many cards as they have; a memory and
   a correction can both be filed in one session. Keep the filed issue links as you go.

4. **Close out** (see below).

## Memory branch

Collect, conversationally:

- **client** — the customer. **Required** — a memory can never be filed without one.
- **product** — the Hive product facet: `wms`, `slotting`, `osci`, or `lm`.
- **version** — the Manhattan version (e.g. WMOS 2020). There is no `version` facet on a memory card,
  so **weave it into the lesson/context** ("On WMOS 2020, …") rather than dropping it.
- **platform** (optional) — `wmos` / `scale` / `scpp`; infer from the product or ask.
- **title** — a short, specific line.
- **lesson** — ask them to **explain the card**: the operational fact, how the client's system behaves
  after the modification.
- **related** (optional) — the core concept(s) it modifies. Use `find_concepts` to locate real ids and
  confirm them; do not invent ids.
- **citations** (optional) — source references.

Then **sanitise before filing**: strip client names from inside the lesson, ticket numbers, and any
personal specifics — state *how the system behaves*, not who said it or which ticket. Show the
sanitised lesson back and get a yes.

File it:

```
submit_memory_promotion(client, product, title, lesson, context?, platform?, related?, citations?)
```

## Correction branch

Collect:

- **target concept id** — the card being corrected. Help them find the exact one with `find_concepts`
  and confirm the id (e.g. `slotting/data-requirements`) before filing.
  - **DB-object cards are not supported yet.** If the target is a schema/table/column/package card (the
    kind you would find with `find_db_objects`), say so plainly: db-card corrections are not yet
    accepted by the pipeline. Offer to capture the discrepancy as a note for follow-up — do **not** file
    it as a correction (it would fail the lint and block the PR).
- **corrected_fact** — ask them to **explain the card**: the correct fact, stated plainly. This is what
  answers will treat as authoritative.
- **rationale** — why the original is wrong or stale; ground it in a source.
- **citations** (encouraged) — source filenames.
- **supersedes** (optional) — correction ids this replaces.

File it:

```
submit_correction(target_concept_id, corrected_fact, rationale, citations?, supersedes?)
```

## Close-out

List the issues you filed (with links) and state the next step plainly, e.g.:

> Filed 2 cards. Next: a reviewer applies the approve-label, a GitHub Action then opens and merges the
> PR, and the card is live in about 15 minutes. Nothing more for you to do — you'll see the PR appear.

The auto-opened PR **is** the "PR with the additions" — the consultant holds no token and does not open
it by hand.

## Non-negotiables

- **Memory needs a client and is sanitised; correction is never client-scoped.** The two tools are
  hard-separated on purpose — never file a lesson as a correction or a product fix as a memory.
- **Ground corrections.** A correction should cite the source that establishes the correct fact; if they
  cannot ground it, say the reviewer will likely ask for one.
- **Read-only for locating cards.** Use `find_concepts` / `find_db_objects` / `resolve` / `get_card` to
  find targets and related ids — never write files or invent ids.
- **Never ask for their email.** hive-author stamps the submitter server-side from the signed-in identity.
- **Fallback if hive-author is absent.** If the `submit_memory_promotion` / `submit_correction` tools are
  not available in this session, do not fail silently — tell the consultant and point them at the GitHub
  Issue Form templates ("Hive Memory promotion" / "Hive Correction") as the manual path.

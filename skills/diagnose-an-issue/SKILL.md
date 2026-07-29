---
name: diagnose-an-issue
description: Use when the user is working a live/production support ticket or diagnosing a problem in a customer's Manhattan WMOS/SCALE system — "why did X fail / not allocate / behave wrong", an error, or an unexpected result. Leads with the customer's own cards, then baseline product behaviour, then prior issues.
---

You are diagnosing a reported issue. Work the Hive cards in this order — customer context first, because issues are reported per customer.

## Playbook
1. **Pin the customer and the symptom.** If either is unclear, ask.
2. **Load the client's cards first** — call the Hive connector's `resolve` with the client set — for client-specific context and any prior issues for that customer.
3. **Load the relevant WMOS/SCALE concept cards** for how the product behaves *out of the box*.
4. **Connect the dots against prior issue cards** for that customer — similar past symptoms, modules, and context (a match is a lead, not necessarily a fix).
5. **Form hypotheses grounded in the cards**, cite `sources:`, and **explicitly separate client-modified behaviour from vanilla product behaviour** — the client's memory says how THEIR system differs.

## Using journal entries
Prior issues are `type: issue` cards — one per past support ticket, tagged by `module`.
- An entry is an **awareness flag, not a diagnosis.** It records what happened and when. Follow its `related` links to the concept card for how the product actually behaves; a match is a lead to check, never a conclusion.
- **`routine: true` marks a routine scheduled request** (a wave run, a batch trigger), not a fault. Down-rank these — they will otherwise crowd out real incidents, since at some clients they are a third of the journal.
- Entries vary in depth. A thin one still tells you this area has history; do not over-read it or infer a cause it does not state.
- **Repetition is signal.** Several entries on the same symptom for the same client is stronger evidence than any single one.

## Non-negotiables
- Cite each card's `sources:`; if the cards don't cover it, say so — don't invent a cause.
- Never blend one client's memory into another client's answer or into core guidance; never blend cards whose regime/product/platform differ.
- Never present a journal entry as a root cause unless it states one.

## Tracking (light)
If the diagnosis spans sessions, you may open an objective (`start_objective` mode='investigate') and log key `finding` / `decision` entries. Otherwise just diagnose — the ticketing system remains the record of the issue.

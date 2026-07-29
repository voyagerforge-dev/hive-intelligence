---
name: plan-an-implementation
description: Use when designing, building, or improving something in Manhattan WMOS/SCALE — creating a new process or configuration, enhancing something that exists, drafting a test plan or specification, or turning a known root cause (from a test cycle or build) into a fix/change plan. Triggers like "help me set this up", "how should we configure X for this client", "let's redesign X", "write a test plan for Y". Warns from the client's own incident history before you design.
---

You are advising on an implementation — either creating something new or making something existing better.

## Playbook
1. **Clarify new-vs-improve** and the concrete goal.
2. **Ground in the cards:** concept cards for how the product works; the client's cards (`resolve` with the client set) for their current setup.
3. **Check the client's incident journal before you design.** Their cards include `type: issue` entries — one per past support ticket, tagged with the `module` it touched. Look for entries in the modules you are about to change, and raise them *before* proposing an approach: "this client has hit X here before" is a design constraint, not a footnote. Several entries in one module is a signal that area is fragile for them.
4. **Brainstorm approaches** and lay out trade-offs, explicitly designing around what the journal shows has failed here before.
5. **Produce the artifact the user needs:** a test plan, a specification outline, or bug-fix guidance from testing. Where the journal shows past failures in scope, turn them into **test cases** — a past incident is the cheapest regression test you will ever get.
6. Cite `sources:`; flag unknowns explicitly rather than guessing.

## Using journal entries
- An entry is an **awareness flag, not an explanation.** It records what happened at this client and when. Follow its `related` links to the concept card for how the product actually behaves — never treat the entry itself as the product's documented behaviour.
- **`routine: true` means a routine scheduled request** (a wave run, a batch trigger), not a fault. Down-rank these; they are operational noise for design purposes, though a large cluster of them is itself worth noticing.
- Entries vary in depth. A thin one still tells you the area has history; do not over-read it or infer a cause it does not state.

## Non-negotiables
- Cite each card's `sources:`; if the cards don't cover it, say so.
- Never blend one client's memory into core guidance or another client's answer; never blend cards whose regime/product/platform differ.
- Never present a journal entry as a root cause unless it states one.

## Tracking (light)
For multi-session work you may open an objective (`start_objective` mode='implement') and log `step` / `decision` / `note` entries. Not required for a single-session plan.

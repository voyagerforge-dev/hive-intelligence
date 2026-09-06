# Skills

Agent skills for working with a Hive corpus. They are **product surface**, which is why they
live here rather than in a deployment's plugin repository.

A skill describes how to use the product: how to answer from cards, how to run a diagnosis,
how to file a correction. That procedure does not depend on whose corpus is loaded or which
hostname serves it. Two deployments of Hive should behave the same way when a consultant
asks the same question, and they only do if the behaviour is defined once, here.

| Skill | What it is for |
|---|---|
| `hive/` | The base skill. Auto-engages and answers from the corpus. |
| `diagnose-an-issue/` | Working a reported problem back to its concepts. |
| `plan-an-implementation/` | Planning a piece of work against what the corpus knows. |
| `learn-a-topic/` | Guided reading across a subject. |
| `contribute/` | Filing a client memory or a correction to a concept card. |

## What lives here and what does not

**Here:** the skill bodies. No hostname, no marketplace metadata, no connector URL.

**Not here:** the packaging, which *is* deployment-specific. A deployment wraps these in a
plugin with its own `.claude-plugin/`, its own `.mcp.json` naming its own MCP endpoint, and
its own marketplace entry, in a repository of its own.

**These are worked examples, not neutral templates.** They are written for the Manhattan WMOS/SCALE
support practice Hive was first built for: the `description:` lines name that vendor's products,
`hive/` names one product's configuration regimes (OPS versus Traditional), and `contribute/`
enumerates one corpus's facet values. The retrieval procedure they describe is general; the nouns
are not. A deployment in another domain is expected to copy these bodies and replace the vocabulary
with its own; nothing in the engine, the card model or the test fixtures requires these nouns.
Generalising the skills upstream so that step is unnecessary is still open work. See
[known limitations](../docs/concepts/principles.md#known-limitations).

A deployment fork inherits this directory the same way it inherits `tooling/` and `docs/`:
by merging `upstream`. That is the whole point of putting them here. A skill fixed once is
fixed for every deployment on the next merge, instead of being fixed in one plugin
repository and quietly rotting in the others.

## Naming

Renamed from OKF to Hive on 2026-07-29, in one commit across everything the name touched:
the base skill's directory and its `name:`, the product references in every skill body, the
author service, and the issue-form templates the Contribute skill cites by title.

It was deferred once on purpose. A skill's `name:` is what invokes it and the templates are
cited by their real titles, so renaming any one of those alone leaves a skill that points at
something that is not there. That is why it is one commit rather than a tidy-up.

The MCP **tool** names are unchanged and were never in scope: they are set by the server, and
`find_concepts` and `submit_memory_promotion` say what they do rather than who they belong to.

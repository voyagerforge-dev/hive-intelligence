# Skills

Agent skills for working with a Hive corpus. They are **product surface**, which is why they
live here rather than in a deployment's plugin repository.

A skill describes how to use the product: how to answer from cards, how to run a diagnosis,
how to file a correction. None of that is specific to whose corpus is loaded or which
hostname serves it. Two deployments of Hive should behave the same way when a consultant
asks the same question, and they only do if the behaviour is defined once, here.

| Skill | What it is for |
|---|---|
| `okf/` | The base skill. Auto-engages and answers from the corpus. |
| `diagnose-an-issue/` | Working a reported problem back to its concepts. |
| `plan-an-implementation/` | Planning a piece of work against what the corpus knows. |
| `learn-a-topic/` | Guided reading across a subject. |
| `contribute/` | Filing a client memory or a correction to a concept card. |

## What lives here and what does not

**Here:** the skill bodies. Deployment-neutral. No hostname, no marketplace metadata, no
connector URL.

**Not here:** the packaging. A deployment wraps these in a plugin with its own
`.claude-plugin/`, its own `.mcp.json` naming its own MCP endpoint, and its own marketplace
entry. The EXAMPLECO deployment does that in `example-org/example-hive-plugin`.

A deployment fork inherits this directory the same way it inherits `tooling/` and `docs/`:
by merging `upstream`. That is the whole point of putting them here. A skill fixed once is
fixed for every deployment on the next merge, instead of being fixed in one plugin
repository and quietly rotting in the others.

## Naming

These still say **OKF** throughout, including the base skill's directory name, which is the
name the product had before it became Hive. The rename is deliberately not done here: the
skill name is what invokes it and the MCP tool names it calls are set by the server, so
renaming is a coordinated change across the skills, `hive-serve`'s tool names and every
deployment's plugin. It is worth doing, and it is worth doing in one commit rather than as a
side effect of a move.

# hive-author

The write door. Files corrections and memory promotions as reviewable issues, so `hive-serve` holds no credentials.

Part of [Hive Intelligence](https://github.com/voyagerforge-dev/hive-intelligence), which turns a body of documentation into
reviewed, git-versioned concept cards and serves them to any MCP or REST client - no vector
index, no embeddings, and no model call at serving time.

**Full documentation: [docs/reference/hive-author.md](https://github.com/voyagerforge-dev/hive-intelligence/blob/main/docs/reference/hive-author.md)**, which covers the command
surface, configuration, behaviour and the things that catch people out.

## Install

**Not published to PyPI.** It is a service that runs in a deployment, not a tool a
consumer installs; see [distributing the engine](https://github.com/voyagerforge-dev/hive-intelligence/blob/main/docs/architecture/engine-distribution.md).
Run it from source, or from the container image built by
`tooling/hive-author/deploy/Dockerfile`.

## From source

```bash
cd tooling/hive-author
uv sync --extra dev     # install
uv run pytest -q        # test
uv run hiveauthor
```

This file is deliberately short. Everything else lives in the reference doc, so there is one
place to keep current rather than two that drift apart.

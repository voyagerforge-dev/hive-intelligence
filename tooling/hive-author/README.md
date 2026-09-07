# hive-author

The write door. Files corrections and memory promotions as reviewable issues, so `hive-serve` holds no credentials.

[![PyPI](https://img.shields.io/pypi/v/vf-hive-author.svg)](https://pypi.org/project/vf-hive-author/)
[![Licence: Apache 2.0](https://img.shields.io/badge/licence-Apache--2.0-blue.svg)](https://github.com/voyagerforge-dev/hive-intelligence/blob/main/LICENSE)

Part of [Hive Intelligence](https://github.com/voyagerforge-dev/hive-intelligence), which turns a body of documentation into
reviewed, git-versioned concept cards and serves them to any MCP or REST client - no vector
index, no embeddings, and no model call at serving time.

**Full documentation: [docs/reference/hive-author.md](https://github.com/voyagerforge-dev/hive-intelligence/blob/main/docs/reference/hive-author.md)**, which covers the command
surface, configuration, behaviour and the things that catch people out.

## Install

```bash
pip install vf-hive-author
```

It is a **service**, not a library: nothing imports it. A deployment installs it at the same
version as the rest of the engine and runs the `hiveauthor` console script it puts on the path -
directly, or from the container image built by `tooling/hive-author/deploy/Dockerfile`. See
[distributing the engine](https://github.com/voyagerforge-dev/hive-intelligence/blob/main/docs/architecture/engine-distribution.md).

## From source

```bash
cd tooling/hive-author
uv sync --extra dev     # install
uv run pytest -q        # test
uv run hiveauthor
```

This file is deliberately short. Everything else lives in the reference doc, so there is one
place to keep current rather than two that drift apart.

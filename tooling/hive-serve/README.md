# hive-serve

Serves cards over REST and MCP, with a per-person work ledger. Stage 3. Calls no model.

[![PyPI](https://img.shields.io/pypi/v/vf-hive-serve.svg)](https://pypi.org/project/vf-hive-serve/)
[![Licence: Apache 2.0](https://img.shields.io/badge/licence-Apache--2.0-blue.svg)](https://github.com/voyagerforge-dev/hive-intelligence/blob/main/LICENSE)

Part of [Hive Intelligence](https://github.com/voyagerforge-dev/hive-intelligence), which turns a body of documentation into
reviewed, git-versioned concept cards and serves them to any MCP or REST client - no vector
index, no embeddings, and no model call at serving time.

**Full documentation: [docs/reference/hive-serve.md](https://github.com/voyagerforge-dev/hive-intelligence/blob/main/docs/reference/hive-serve.md)**, which covers the command
surface, configuration, behaviour and the things that catch people out.

## Install

```bash
pip install vf-hive-serve
hiveserve serve --help
```

`hiveserve serve` needs a corpus (`CONCEPTS_DIR`) and a Postgres ledger (`LEDGER_DSN`),
and refuses to start without either. [Getting started](https://github.com/voyagerforge-dev/hive-intelligence/blob/main/docs/guides/getting-started.md)
walks the whole thing from a clean checkout in about five minutes.

## From source

```bash
cd tooling/hive-serve
uv sync --extra dev     # install
uv run pytest -q        # test
uv run hiveserve serve --http
```

This file is deliberately short. Everything else lives in the reference doc, so there is one
place to keep current rather than two that drift apart.

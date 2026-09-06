# hive-zendesk

Closed support tickets to client-scoped issue cards.

[![PyPI](https://img.shields.io/pypi/v/vf-hive-zendesk.svg)](https://pypi.org/project/vf-hive-zendesk/)
[![Licence: Apache 2.0](https://img.shields.io/badge/licence-Apache--2.0-blue.svg)](https://github.com/voyagerforge-dev/hive-intelligence/blob/main/LICENSE)

Part of [Hive Intelligence](https://github.com/voyagerforge-dev/hive-intelligence), which turns a body of documentation into
reviewed, git-versioned concept cards and serves them to any MCP or REST client - no vector
index, no embeddings, and no model call at serving time.

**Full documentation: [docs/reference/hive-zendesk.md](https://github.com/voyagerforge-dev/hive-intelligence/blob/main/docs/reference/hive-zendesk.md)**, which covers the command
surface, configuration, behaviour and the things that catch people out.

## Install

```bash
pip install vf-hive-zendesk
hivezendesk --help
```

## From source

```bash
cd tooling/hive-zendesk
uv sync --extra dev     # install
uv run pytest -q        # test
uv run hivezendesk --help
```

This file is deliberately short. Everything else lives in the reference doc, so there is one
place to keep current rather than two that drift apart.

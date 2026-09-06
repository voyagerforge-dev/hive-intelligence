# hive-gen

Atomic markdown to reviewed concept cards. Stage 2, and the card model.

[![PyPI](https://img.shields.io/pypi/v/vf-hive-gen.svg)](https://pypi.org/project/vf-hive-gen/)
[![Licence: Apache 2.0](https://img.shields.io/badge/licence-Apache--2.0-blue.svg)](https://github.com/voyagerforge-dev/hive-intelligence/blob/main/LICENSE)

Part of [Hive Intelligence](https://github.com/voyagerforge-dev/hive-intelligence), which turns a body of documentation into
reviewed, git-versioned concept cards and serves them to any MCP or REST client - no vector
index, no embeddings, and no model call at serving time.

**Full documentation: [docs/reference/hive-gen.md](https://github.com/voyagerforge-dev/hive-intelligence/blob/main/docs/reference/hive-gen.md)**, which covers the command
surface, configuration, behaviour and the things that catch people out.

## Install

```bash
pip install vf-hive-gen
python -m hivegen.run
```

## From source

```bash
cd tooling/hive-gen
uv sync --extra dev     # install
uv run pytest -q        # test
uv run python -m hivegen.run
```

This file is deliberately short. Everything else lives in the reference doc, so there is one
place to keep current rather than two that drift apart.

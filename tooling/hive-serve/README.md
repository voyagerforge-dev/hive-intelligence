# hive-serve

Serves cards over REST and MCP, with a per-person work ledger. Stage 3. Calls no model.

Part of [Hive Intelligence](../../README.md). **Full documentation:
[docs/reference/hive-serve.md](../../docs/reference/hive-serve.md)**, which covers the command surface,
configuration, behaviour and the things that catch people out.

```bash
uv sync --extra dev     # install
uv run pytest -q        # test
uv run hiveserve       # run
```

This file is deliberately short. Everything else lives in the reference doc, so there is one place
to keep current rather than two that drift apart.

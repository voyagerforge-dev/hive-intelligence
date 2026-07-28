# hive-author

The write door. Files corrections and memory promotions as reviewable issues, so hive-serve holds no credentials.

Part of [Hive Intelligence](../../README.md). **Full documentation:
[docs/reference/hive-author.md](../../docs/reference/hive-author.md)**, which covers the command surface,
configuration, behaviour and the things that catch people out.

```bash
uv sync --extra dev     # install
uv run pytest -q        # test
uv run hiveauthor       # run
```

This file is deliberately short. Everything else lives in the reference doc, so there is one place
to keep current rather than two that drift apart.

# hive-dbparse

Database schema DDL to cards. Deterministic, with no model involved.

Part of [Hive Intelligence](../../README.md). **Full documentation:
[docs/reference/hive-dbparse.md](../../docs/reference/hive-dbparse.md)**, which covers the command surface,
configuration, behaviour and the things that catch people out.

```bash
uv sync --extra dev     # install
uv run pytest -q        # test
uv run hivedbparse       # run
```

This file is deliberately short. Everything else lives in the reference doc, so there is one place
to keep current rather than two that drift apart.

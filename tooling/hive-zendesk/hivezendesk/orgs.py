"""Resolve client code -> Zendesk organization ids from the customer master."""
from __future__ import annotations

from pathlib import Path

import yaml


def load_org_ids(customers_yaml_path: str | Path, clients: list[str]) -> dict[str, list[int]]:
    data = yaml.safe_load(Path(customers_yaml_path).read_text()) or {}
    by_code = {c.get("code"): c for c in (data.get("customers") or []) if c.get("code")}
    out: dict[str, list[int]] = {}
    for code in clients:
        entry = by_code.get(code)
        if entry is None:
            raise KeyError(f"client {code!r} not found in customer master")
        ids = [int(o["id"]) for o in (entry.get("zendesk_orgs") or []) if o.get("id")]
        if not ids:
            raise KeyError(f"client {code!r} has no zendesk_orgs")
        out[code] = ids
    return out

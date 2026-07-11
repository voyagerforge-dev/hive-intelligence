"""Resolve the caller's owner id from a trusted proxy header, else the configured default."""
from __future__ import annotations


def resolve_owner(headers, settings) -> str:
    name = settings.identity_header
    val = None
    if headers is not None:
        try:
            val = headers.get(name)
            if not val:
                low = {str(k).lower(): v for k, v in dict(headers).items()}
                val = low.get(name.lower())
        except (AttributeError, TypeError, ValueError):
            val = None
    return val or settings.okf_default_owner

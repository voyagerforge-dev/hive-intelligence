"""Strip personal identifiers BEFORE the LLM sees anything, and detect residual leaks after.

Two-sided by design: scrubbing is best-effort, so `leaks()` is the hard assertion the
verification gate runs against every emitted card.
"""
from __future__ import annotations

import re

from .model import Ticket

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Deliberately loose: over-redacting a number is safe, leaking a phone number is not.
_PHONE = re.compile(r"(?:(?<=\s)|^)(?:\+?\d[\d\s().-]{7,}\d)(?=\s|$|[.,;])")

MIN_NAME_LEN = 3


def known_values(t: Ticket, extra_names: list[str] | None = None) -> set[str]:
    """Personal values associated with this ticket, from structured fields."""
    out: set[str] = set()
    for n in (extra_names or []):
        n = (n or "").strip()
        if len(n) >= MIN_NAME_LEN:
            out.add(n)
    for m in _EMAIL.finditer(t.thread_text()):
        out.add(m.group(0))
    return out


def scrub_text(text: str, known: set[str]) -> str:
    out = text or ""
    for value in sorted(known, key=len, reverse=True):
        if not value.strip():
            continue
        token = "[email]" if _EMAIL.fullmatch(value) else "[name]"
        out = re.sub(re.escape(value), token, out, flags=re.IGNORECASE)
    out = _EMAIL.sub("[email]", out)
    out = _PHONE.sub(" [phone]", out)
    return out


def leaks(text: str, known: set[str]) -> list[str]:
    """Personal values still present. Non-empty means the run must fail."""
    hay = (text or "").lower()
    found = [v for v in known if v.strip() and v.lower() in hay]
    if _EMAIL.search(text or ""):
        found.append("<email-pattern>")
    return sorted(set(found))

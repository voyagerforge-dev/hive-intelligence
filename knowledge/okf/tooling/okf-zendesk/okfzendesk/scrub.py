"""Strip personal identifiers BEFORE the LLM sees anything, and detect residual leaks after.

Two-sided by design: scrubbing is best-effort, so `leaks()` is the hard assertion the
verification gate runs against every emitted card.
"""
from __future__ import annotations

import re

from .model import Ticket

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Phone and SA-ID patterns carried over from the retired zendesk-ingest-svc, which ran
# against this exact ticket corpus. ALPHA and BETA are South African, so 13-digit national
# ID numbers are a real presence and a real DPA exposure.
_PHONE = re.compile(
    r"(?<!\d)(?:\+\d[\d\s\-]{6,}\d|\(?\d{2,4}\)?[\s\-]\d{3}[\s\-]?\d{2,4})(?!\d)"
)
_SA_ID = re.compile(r"(?<!\d)\d{13}(?!\d)")

_PATTERNS = {"email": _EMAIL, "phone": _PHONE, "sa_id": _SA_ID}

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
    out = _SA_ID.sub("[id]", out)
    out = _PHONE.sub(" [phone]", out)
    return out


def leaks(text: str, known: set[str]) -> list[str]:
    """PII *kinds* still present, e.g. ["email", "known-name"]. Never the values.

    Returning kinds rather than values is deliberate: the result is put in error messages,
    run reports and logs, so returning the offending value would leak the very data this
    function exists to protect. (Carried over from the retired service's find_pii.)
    """
    hay = (text or "").lower()
    kinds = [kind for kind, rx in _PATTERNS.items() if rx.search(text or "")]
    if any(v.strip() and v.lower() in hay for v in known):
        kinds.append("known-name")
    return sorted(set(kinds))

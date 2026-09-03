"""Strip personal identifiers BEFORE the LLM sees anything, and detect residual leaks after.

Two-sided by design: scrubbing is best-effort, so `leaks()` is the hard assertion the
verification gate runs against every emitted card.
"""
from __future__ import annotations

import re

from .model import Ticket

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Phone and national-ID patterns carried over from the retired zendesk-ingest-svc. Support
# tickets carry personal identifiers in free text, and a national ID number written into a
# card on disk is a real data-protection exposure.
_PHONE = re.compile(
    r"(?<!\d)(?:\+\d[\d\s\-]{6,}\d|\(?\d{2,4}\)?[\s\-]\d{3}[\s\-]?\d{2,4})(?!\d)"
)
# A bare 13-digit match is not enough: WMS ticket subjects carry long numeric LPN, wave
# and item identifiers, and treating those as national IDs quarantined legitimate cards.
# The 13-digit format checked here is YYMMDD + sequence + citizenship digit + Luhn check
# digit, so all three structural properties are required before calling it PII.
_THIRTEEN = re.compile(r"(?<!\d)\d{13}(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def is_sa_id(digits: str) -> bool:
    if len(digits) != 13 or not digits.isdigit():
        return False
    month, day = int(digits[2:4]), int(digits[4:6])
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return False
    return _luhn_ok(digits)


class _SAIdPattern:
    """Duck-types the re interface used by _PATTERNS/scrub, adding structural validation."""

    @staticmethod
    def search(text: str):
        for m in _THIRTEEN.finditer(text or ""):
            if is_sa_id(m.group()):
                return m
        return None

    @staticmethod
    def sub(repl: str, text: str) -> str:
        return _THIRTEEN.sub(lambda m: repl if is_sa_id(m.group()) else m.group(), text or "")


_SA_ID = _SAIdPattern()

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

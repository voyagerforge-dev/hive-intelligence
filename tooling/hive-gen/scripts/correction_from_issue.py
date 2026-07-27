"""Parse a Correction Issue Form body into a record and write a correction card.
Called by .github/workflows/correction-from-issue.yml.
Usage: python scripts/correction_from_issue.py <issue_body_file> <concepts_dir>  -> prints card path"""
import re
import sys
from datetime import date
from pathlib import Path

from hivegen.corrections import record_to_correction

ALLOWED_PRODUCTS = {"wms", "osci", "slotting", "labour-management"}


def _field(body: str, heading: str) -> str:
    m = re.search(rf"(?ms)^###\s*{re.escape(heading)}\s*\n(.*?)(?=\n###|\Z)", body)
    val = (m.group(1).strip() if m else "")
    return "" if val == "_No response_" else val


def parse_issue(body: str) -> dict:
    corrects = _field(body, "Target concept id")
    product = corrects.split("/", 1)[0] if "/" in corrects else ""
    cites = [ln.strip() for ln in _field(body, "Citation source files").splitlines() if ln.strip()]
    sup = [ln.strip() for ln in _field(body, "Supersedes (optional)").splitlines() if ln.strip()]
    correction = _field(body, "Corrected fact")
    return {
        "corrects": corrects, "product": product,
        "title": correction[:70] or f"Correction to {corrects}",
        "description": f"Correction to {corrects}.",
        "correction": correction, "rationale": _field(body, "Rationale"),
        "citations": cites, "supersedes": sup, "status": "approved",
        "timestamp": date.today().isoformat(),
    }


def _slug(t): return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:60]


def validate_record(rec: dict) -> None:
    """Reject records whose corrects/product could escape concepts/<product>/corrections/.
    Raises ValueError on any unsafe value."""
    corrects = rec.get("corrects", "")
    product = rec.get("product", "")
    if "/" not in corrects:
        raise ValueError(f"invalid Target concept id '{corrects}': expected '<product>/<concept>'")
    if product not in ALLOWED_PRODUCTS:
        raise ValueError(f"unknown product '{product}': must be one of {sorted(ALLOWED_PRODUCTS)}")
    # defense in depth: no traversal / absolute segments anywhere in the id
    if ".." in corrects.split("/") or corrects.startswith("/"):
        raise ValueError(f"unsafe Target concept id '{corrects}'")


if __name__ == "__main__":  # pragma: no cover
    body = Path(sys.argv[1]).read_text()
    concepts = sys.argv[2]
    rec = parse_issue(body)
    try:
        validate_record(rec)
    except ValueError as e:
        raise SystemExit(str(e))
    d = Path(concepts) / rec["product"] / "corrections"
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{_slug(rec['title'])}.md"
    out.write_text(record_to_correction(rec))
    print(out)

"""Parse a Correction Issue Form body into a record and write a correction card.
Called by the corpus repository's correction-from-issue workflow.
Usage: hivegen-correction-from-issue <issue_body_file> <concepts_dir>  -> prints card path"""
import argparse
import re
from datetime import UTC, datetime
from pathlib import Path

from hivegen.corrections import record_to_correction
from hivegen.profile import load_profile

# Valid `product:` facet values, from the corpus profile. An empty set means the profile
# does not declare them, and the check is skipped: a hardcoded list rejects every product
# that exists in some other corpus, which is a validator that fails closed on valid data.
ALLOWED_PRODUCTS = set(load_profile().card_products)


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
        "timestamp": datetime.now(UTC).date().isoformat(),
    }


def _slug(t): return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:60]


def validate_record(rec: dict) -> None:
    """Reject records whose corrects/product could escape concepts/<product>/corrections/.
    Raises ValueError on any unsafe value."""
    corrects = rec.get("corrects", "")
    product = rec.get("product", "")
    if "/" not in corrects:
        raise ValueError(f"invalid Target concept id '{corrects}': expected '<product>/<concept>'")
    if ALLOWED_PRODUCTS and product not in ALLOWED_PRODUCTS:
        raise ValueError(f"unknown product '{product}': must be one of {sorted(ALLOWED_PRODUCTS)}")
    # defense in depth: no traversal / absolute segments anywhere in the id
    if ".." in corrects.split("/") or corrects.startswith("/"):
        raise ValueError(f"unsafe Target concept id '{corrects}'")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="hivegen-correction-from-issue",
        description="Parse a Correction issue-form body into a correction card and write it, "
                    "printing the path written.")
    ap.add_argument("issue_body_file", help="a file holding the issue body")
    ap.add_argument("concepts_dir", help="the corpus concepts/ tree to write into")
    args = ap.parse_args(argv)
    rec = parse_issue(Path(args.issue_body_file).read_text())
    try:
        validate_record(rec)
    except ValueError as e:
        raise SystemExit(str(e)) from e
    d = Path(args.concepts_dir) / rec["product"] / "corrections"
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{_slug(rec['title'])}.md"
    out.write_text(record_to_correction(rec))
    print(out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

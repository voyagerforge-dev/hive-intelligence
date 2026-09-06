"""Parse a Memory Issue Form body into a record and write a client-memory card.
Called by the corpus repository's memory-from-issue workflow.
Usage: hivegen-memory-from-issue <issue_body_file> <clients_dir>  -> prints card path"""
import argparse
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from hivegen.corpus import require_dir
from hivegen.memory import record_to_memory
from hivegen.profile import load_profile

# Valid `product:` facet values, from the corpus profile. An empty set means the profile
# does not declare them, and the check is skipped: a hardcoded list rejects every product
# that exists in some other corpus, which is a validator that fails closed on valid data.
ALLOWED_PRODUCTS = set(load_profile().card_products)
# The base a memory card's id resolves under. Same lookup and same default as
# `conformance_pass.BASE_URL`, which carries the rationale: a card is a path, not a host,
# because it outlives any one deployment's hostname. The two card-writing scripts have to
# agree, or a corpus ends up with concept cards on a path and memory cards on a hostname.
BASE_URL = os.environ.get("CARD_BASE_URL", "/card")
_CLIENT_RE = re.compile(r"\A[a-z0-9-]+\Z")  # \A..\Z (not ^..$): reject a trailing newline too


def _field(body: str, heading: str) -> str:
    m = re.search(rf"(?ms)^###\s*{re.escape(heading)}\s*\n(.*?)(?=\n###|\Z)", body)
    val = (m.group(1).strip() if m else "")
    return "" if val == "_No response_" else val


def _lines(body: str, heading: str) -> list:
    return [ln.strip() for ln in _field(body, heading).splitlines() if ln.strip()]


def _slug(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:60]


def resource_for(client: str, slug: str) -> str:
    return f"{BASE_URL}/clients/{client}/memory/{slug}"


def parse_issue(body: str) -> dict:
    client = _field(body, "Client").strip().lower()
    product = _field(body, "Product").strip().lower()
    lesson = _field(body, "The lesson (de-personalised)")
    title = _field(body, "Title") or lesson[:70]
    return {
        "client": client, "product": product, "title": title,
        "description": f"{client} memory: {title}",
        "memory": lesson, "context": _field(body, "When it applies"),
        "platform": _field(body, "Platform (optional)").lower(),
        "related": _lines(body, "Related concept ids (optional)"),
        "citations": _lines(body, "Citation source files (optional)"),
        "tags": [], "supersedes": [], "status": "approved",
        "timestamp": datetime.now(UTC).date().isoformat(),
    }


def validate_record(rec: dict) -> None:
    client = rec.get("client", "")
    product = rec.get("product", "")
    if ALLOWED_PRODUCTS and product not in ALLOWED_PRODUCTS:
        raise ValueError(f"unknown product '{product}': must be one of {sorted(ALLOWED_PRODUCTS)}")
    if not _CLIENT_RE.match(client) or client in ("..", ""):
        raise ValueError(f"unsafe client '{client}': must match [a-z0-9-]+")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="hivegen-memory-from-issue",
        description="Parse a Memory issue-form body into a client-memory card and write it, "
                    "printing the path written.")
    ap.add_argument("issue_body_file", help="a file holding the issue body")
    ap.add_argument("clients_dir", help="the corpus clients/ tree to write into")
    args = ap.parse_args(argv)
    clients = require_dir(args.clients_dir, setting="clients_dir",
                          what="the corpus tree to write the card into")
    rec = parse_issue(Path(args.issue_body_file).read_text())
    try:
        validate_record(rec)
    except ValueError as e:
        raise SystemExit(str(e)) from e
    slug = _slug(rec["title"])
    rec["submitted_by"] = os.environ.get("ISSUE_AUTHOR", "")
    rec["resource"] = resource_for(rec["client"], slug)
    d = clients / rec["client"] / "memory"
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{slug}.md"
    out.write_text(record_to_memory(rec))
    print(out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

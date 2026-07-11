"""Parse a Memory Issue Form body into a record and write a client-memory card.
Called by .github/workflows/memory-from-issue.yml.
Usage: python scripts/memory_from_issue.py <issue_body_file> <clients_dir>  -> prints card path"""
import re
import sys
from datetime import date
from pathlib import Path

from okfgen.memory import record_to_memory

ALLOWED_PRODUCTS = {"wms", "osci", "slotting", "labour-management"}
BASE_URL = "https://hive.example.com/card"
_CLIENT_RE = re.compile(r"^[a-z0-9-]+$")


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
        "timestamp": date.today().isoformat(),
    }


def validate_record(rec: dict) -> None:
    client = rec.get("client", "")
    product = rec.get("product", "")
    if product not in ALLOWED_PRODUCTS:
        raise ValueError(f"unknown product '{product}': must be one of {sorted(ALLOWED_PRODUCTS)}")
    if not _CLIENT_RE.match(client) or client in ("..", ""):
        raise ValueError(f"unsafe client '{client}': must match [a-z0-9-]+")


if __name__ == "__main__":  # pragma: no cover
    body = Path(sys.argv[1]).read_text()
    clients = sys.argv[2]
    rec = parse_issue(body)
    try:
        validate_record(rec)
    except ValueError as e:
        raise SystemExit(str(e))
    slug = _slug(rec["title"])
    rec["submitted_by"] = ""
    rec["resource"] = resource_for(rec["client"], slug)
    d = Path(clients) / rec["client"] / "memory"
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{slug}.md"
    out.write_text(record_to_memory(rec))
    print(out)

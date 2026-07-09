"""Pure record⇄card serialization seam for OKF correction cards.
A `record` is a surface-agnostic dict; a `correction card` is conformant markdown at
concepts/<product>/corrections/<slug>.md. The CLI (new_correction.py) and the GitHub
Issue-Form Action both author cards through record_to_correction. `resource` and the
`# Citations` body section are added later by scripts/conformance_pass.py, not here."""
from __future__ import annotations

import re

import yaml


def record_to_correction(record: dict) -> str:
    fm = {
        "type": "correction",
        "title": record["title"],
        "description": record.get("description", ""),
        "corrects": record["corrects"],
        "supersedes": record.get("supersedes", []),
        "tags": record.get("tags", []),
        "product": record["product"],
        "resource": "",   # empty placeholder — conformance_pass fills it from the file path
        "sources": [{"kind": "correction-source", "ref": r} for r in record.get("citations", [])],
        "timestamp": record.get("timestamp", ""),
        "status": record.get("status", "approved"),
    }
    fm_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip("\n")
    body = f"## Correction\n\n{record['correction'].rstrip()}\n\n## Rationale\n\n{record.get('rationale','').rstrip()}\n"
    return f"---\n{fm_text}\n---\n\n{body}"


def _section(body: str, heading: str) -> str:
    m = re.search(rf"(?ms)^{re.escape(heading)}\s*\n(.*?)(?=\n#|\Z)", body)
    return m.group(1).strip() if m else ""


_FRONTMATTER_RE = re.compile(r"(?s)^---\s*\n(.*?)\n---\s*\n?(.*)$")


def correction_to_record(card_text: str) -> dict:
    m = _FRONTMATTER_RE.match(card_text)
    if not m:
        fm: dict = {}
        body = ""
    else:
        fm = yaml.safe_load(m.group(1)) or {}
        body = m.group(2)
    return {
        "corrects": fm.get("corrects", ""),
        "title": fm.get("title", ""),
        "description": fm.get("description", ""),
        "correction": _section(body, "## Correction"),
        "rationale": _section(body, "## Rationale"),
        "citations": [s.get("ref") for s in (fm.get("sources") or []) if isinstance(s, dict)],
        "supersedes": fm.get("supersedes", []),
        "product": fm.get("product", ""),
        "status": fm.get("status", "approved"),
        "timestamp": fm.get("timestamp", ""),
    }

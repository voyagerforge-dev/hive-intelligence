"""Read WMOS reference markdown from R2 and filter to the Wave/Replenishment slice."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Wave/Replenishment functional area — name-keyword match (refined against real listing).
_WAVE_REPLEN = ("wave", "replen", "replenishment", "shipping-wave", "pre-wave",
                "fs-300", "fs300", "outbound-planning", "wave-inquiry")


def is_wave_replen(name: str) -> bool:
    low = name.lower()
    return any(kw in low for kw in _WAVE_REPLEN)


@dataclass(frozen=True)
class Doc:
    id: str
    name: str
    text: str


def load_docs(s3, bucket: str, prefix: str, *, only_wave_replen: bool = True) -> list[Doc]:
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    out: list[Doc] = []
    for obj in resp.get("Contents", []):
        key = obj["Key"]
        if not key.endswith(".md"):
            continue
        if only_wave_replen and not is_wave_replen(key):
            continue
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        text = body.decode() if isinstance(body, bytes) else str(body)
        out.append(Doc(id=key, name=key, text=text))
    return out


def load_docs_local(root, *, only_wave_replen: bool = True) -> list[Doc]:
    """Read clean atomic markdown from a local directory (e.g. wms-work/atomic/).

    Same Doc shape as ``load_docs`` so the rest of the pipeline is source-agnostic.
    The Docling/scpp-prep flow never writes markdown to R2, so the curated atomic
    markdown lives on disk; this loader feeds it straight into the OKF pipeline.
    """
    root = Path(root)
    out: list[Doc] = []
    for path in sorted(root.glob("*.md")):
        name = path.name
        if only_wave_replen and not is_wave_replen(name):
            continue
        out.append(Doc(id=name, name=name, text=path.read_text()))
    return out

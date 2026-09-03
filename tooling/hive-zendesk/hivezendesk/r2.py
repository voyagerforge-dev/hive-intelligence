"""Read the already-distilled ticket cards staged on R2 by the retired zendesk-ingest-svc.

Those ~2,300 cards represent distillation work already paid for, so the journal is built by
reshaping them rather than re-running the model over full ticket threads (roughly half the
time per entry, and none of it repeated).

Layout written by the old service (`stage.py`):
    support_<client>/docs/<client>-<ticket_id>-<slug>.md
    support_<client>/_manifest.jsonl

NB the manifest is NOT an index: `write_manifest` overwrote it with each run's batch, so a
prefix holding 892 cards can carry a 2-line manifest. Identity is therefore derived from the
object key, which is complete and stable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

KEY_RE = re.compile(r"^support_(?P<client>[a-z0-9_-]+)/docs/"
                    r"(?P=client)-(?P<ticket>\d+)-.*\.md$")

# The old cards lead with an H1 title, which is better than re-deriving one from the slug.
H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class StagedCard:
    key: str
    client: str
    ticket_id: int
    text: str

    def title(self) -> str:
        m = H1_RE.search(self.text or "")
        return m.group(1).strip() if m else ""


def parse_key(key: str) -> tuple[str, int] | None:
    """`support_alpha/docs/alpha-10928-pallet-label.md` -> ("alpha", 10928). None if unrecognised."""
    m = KEY_RE.match(key or "")
    if not m:
        return None
    return m.group("client"), int(m.group("ticket"))


class R2Reader:
    """Read-only view of the staged cards. Never writes: the bucket is the old service's
    output and other datasets share it, so a write here would land in data this tool does
    not own."""

    def __init__(self, s3_client, bucket: str) -> None:
        self._s3 = s3_client
        self._bucket = bucket

    def list_cards(self, client: str) -> list[str]:
        keys: list[str] = []
        token = None
        while True:
            kw = {"Bucket": self._bucket, "Prefix": f"support_{client}/docs/", "MaxKeys": 1000}
            if token:
                kw["ContinuationToken"] = token
            page = self._s3.list_objects_v2(**kw)
            keys += [o["Key"] for o in page.get("Contents", [])]
            if not page.get("IsTruncated"):
                return keys
            token = page.get("NextContinuationToken")

    def get_card(self, key: str) -> StagedCard | None:
        parsed = parse_key(key)
        if parsed is None:
            return None
        client, ticket_id = parsed
        body = self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        return StagedCard(key=key, client=client, ticket_id=ticket_id,
                          text=body.decode("utf-8", errors="replace"))

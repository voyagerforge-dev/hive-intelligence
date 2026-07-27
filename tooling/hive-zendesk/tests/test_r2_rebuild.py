import json

from hivezendesk.r2 import R2Reader, StagedCard, parse_key
from hivezendesk.rebuild import rebuild, ticket_meta

CARD = """# Add Date, Time and User Stamp to Pallet Labels

## Problem
Staff could not identify who printed unscannable labels.

## Resolution
Label design updated to include date, time and user stamp.
"""


def test_parse_key_extracts_client_and_ticket():
    assert parse_key("support_alpha/docs/alpha-10928-pallet-label.md") == ("alpha", 10928)
    assert parse_key("support_beta/docs/beta-7-x.md") == ("beta", 7)


def test_parse_key_rejects_foreign_or_malformed_keys():
    # other datasets share this bucket; they must never be mistaken for ticket cards
    assert parse_key("example_prefix/docs/something.md") is None
    assert parse_key("support_alpha/_manifest.jsonl") is None
    assert parse_key("support_alpha/docs/alpha-notanumber-x.md") is None


def test_staged_card_title_comes_from_the_h1():
    c = StagedCard("k", "alpha", 1, CARD)
    assert c.title() == "Add Date, Time and User Stamp to Pallet Labels"
    assert StagedCard("k", "alpha", 1, "no heading here").title() == ""


class FakeS3:
    def __init__(self, keys):
        self._keys = keys

    def list_objects_v2(self, **kw):
        pref = kw["Prefix"]
        return {"Contents": [{"Key": k} for k in self._keys if k.startswith(pref)],
                "IsTruncated": False}

    def get_object(self, Bucket, Key):  # noqa: N803 - boto3 signature
        class B:
            @staticmethod
            def read():
                return CARD.encode()
        return {"Body": B()}


class FakeConnector:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def list_closed(self, org_id, since):
        self.calls += 1
        return self.rows


ENTRY = {"what_happened": "Labels could not be traced to a printer.",
         "how_it_closed": "Label design updated.",
         "module": "labelling", "tags": ["labels", "pallet"],
         "related_candidates": [], "routine": False}


class FakeLLM:
    """Honours the batch contract: an array when asked for one, else a single object."""

    def __init__(self, mode="ok"):
        self.calls = 0
        self.mode = mode

    def complete(self, system, user):
        self.calls += 1
        n = user.count("### CARD")
        if n > 1:                                   # batched request
            if self.mode == "unparsable":
                return "sorry, no JSON here"
            if self.mode == "miscount":
                return json.dumps([ENTRY] * (n - 1))   # one short -> misalignment
            return json.dumps([ENTRY] * n)
        return json.dumps(ENTRY)


KEYS = ["support_alpha/docs/alpha-10928-pallet-label.md",
        "support_alpha/docs/alpha-10938-ship-confirm.md",
        "example_prefix/docs/ignore-me.md"]
ROWS = [{"id": 10928, "updated_at": "2026-03-14T09:00:00Z", "subject": "Pallet label change"},
        {"id": 10938, "updated_at": "2026-04-01T09:00:00Z", "subject": "Missing ship confirm"}]


def test_ticket_meta_is_one_call_per_org_not_per_ticket():
    conn = FakeConnector(ROWS)
    meta = ticket_meta(conn, [1, 2, 3])
    assert conn.calls == 3                     # per org, not per ticket
    assert meta[10928] == ("2026-03-14T09:00:00Z", "Pallet label change")


def test_rebuild_writes_entries_from_staged_cards(tmp_path):
    (tmp_path / "concepts").mkdir()
    llm = FakeLLM()
    report = rebuild(clients=["alpha"], org_ids={"alpha": [1]},
                     r2=R2Reader(FakeS3(KEYS), "bucket"), connector=FakeConnector(ROWS), llm=llm,
                     clients_dir=tmp_path / "clients", concepts_dir=tmp_path / "concepts",
                     workers=2)
    assert report.emitted == 2                 # the foreign example_prefix key is not listed
    assert llm.calls == 1                      # both cards in ONE batched call
    written = sorted(p.name for p in (tmp_path / "clients" / "alpha" / "issues").glob("*.md"))
    assert written[0].startswith("10928-")
    body = (tmp_path / "clients" / "alpha" / "issues" / written[0]).read_text()
    assert "type: issue" in body and "module: labelling" in body
    assert "## What happened" in body


def test_rebuild_dry_run_calls_no_model_and_writes_nothing(tmp_path):
    (tmp_path / "concepts").mkdir()
    llm = FakeLLM()
    report = rebuild(clients=["alpha"], org_ids={"alpha": [1]},
                     r2=R2Reader(FakeS3(KEYS), "bucket"), connector=FakeConnector(ROWS), llm=llm,
                     clients_dir=tmp_path / "clients", concepts_dir=tmp_path / "concepts",
                     dry_run=True)
    assert llm.calls == 0 and report.emitted == 2
    assert not (tmp_path / "clients").exists()


def test_rebuild_skips_entries_already_written(tmp_path):
    (tmp_path / "concepts").mkdir()
    kw = dict(clients=["alpha"], org_ids={"alpha": [1]},
              r2=R2Reader(FakeS3(KEYS), "bucket"), connector=FakeConnector(ROWS),
              clients_dir=tmp_path / "clients", concepts_dir=tmp_path / "concepts", workers=2)
    rebuild(llm=FakeLLM(), **kw)
    second = FakeLLM()
    report = rebuild(llm=second, **kw)
    assert second.calls == 0 and report.cached == 2


def test_batch_falls_back_to_singles_when_reply_is_unparsable(tmp_path):
    (tmp_path / "concepts").mkdir()
    llm = FakeLLM(mode="unparsable")
    report = rebuild(clients=["alpha"], org_ids={"alpha": [1]},
                     r2=R2Reader(FakeS3(KEYS), "bucket"), connector=FakeConnector(ROWS), llm=llm,
                     clients_dir=tmp_path / "clients", concepts_dir=tmp_path / "concepts",
                     workers=1, batch_size=5)
    # 1 failed batch call + 2 individual retries, and both entries still land
    assert llm.calls == 3
    assert report.emitted == 2


def test_batch_falls_back_when_the_count_does_not_match(tmp_path):
    """A short array would otherwise attach one ticket's summary to another ticket's id."""
    (tmp_path / "concepts").mkdir()
    llm = FakeLLM(mode="miscount")
    report = rebuild(clients=["alpha"], org_ids={"alpha": [1]},
                     r2=R2Reader(FakeS3(KEYS), "bucket"), connector=FakeConnector(ROWS), llm=llm,
                     clients_dir=tmp_path / "clients", concepts_dir=tmp_path / "concepts",
                     workers=1, batch_size=5)
    assert llm.calls == 3
    assert report.emitted == 2
    # each entry must carry its OWN ticket id
    names = sorted(p.name.split("-")[0] for p in
                   (tmp_path / "clients" / "alpha" / "issues").glob("*.md"))
    assert names == ["10928", "10938"]


class CountingS3(FakeS3):
    """Counts body downloads, so we can assert we do not pay for cards already carded."""

    def __init__(self, keys):
        super().__init__(keys)
        self.gets = 0

    def get_object(self, Bucket, Key):  # noqa: N803 - boto3 signature
        self.gets += 1
        return super().get_object(Bucket=Bucket, Key=Key)


def test_already_carded_tickets_are_not_downloaded_from_r2(tmp_path):
    """The key alone yields the ticket id, so a cached ticket needs no body fetch.

    The first full run spent 7m23s re-downloading 1,132 cards it then discarded.
    """
    (tmp_path / "concepts").mkdir()
    kw = dict(clients=["alpha"], org_ids={"alpha": [1]}, connector=FakeConnector(ROWS),
              clients_dir=tmp_path / "clients", concepts_dir=tmp_path / "concepts", workers=1)
    s3 = CountingS3(KEYS)
    rebuild(r2=R2Reader(s3, "bucket"), llm=FakeLLM(), **kw)
    first = s3.gets
    assert first == 2                      # both cards fetched on the first pass

    s3b = CountingS3(KEYS)
    report = rebuild(r2=R2Reader(s3b, "bucket"), llm=FakeLLM(), **kw)
    assert report.cached == 2
    assert s3b.gets == 0                   # second pass downloads nothing

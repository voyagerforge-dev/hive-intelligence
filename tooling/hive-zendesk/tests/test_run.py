import json
from importlib import metadata

import pytest

import hivezendesk
from hivezendesk.fm import parse_frontmatter
from hivezendesk.run import ingest


class FakeConnector:
    def __init__(self, rows, comments):
        self.rows = rows
        self.comments = comments

    def list_closed(self, org_id, since):
        return self.rows

    def get_ticket(self, ticket_id):
        return {"comments": self.comments}


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        return json.dumps({"what_happened": "Wave did not allocate", "how_it_closed": "reran",
                           "module": "allocation", "tags": ["allocation"],
                           "related_candidates": [], "routine": False})


ROW = {"id": 14872, "subject": "Orders not allocating",
       "description": "The morning wave is stuck and nothing allocated for the whole shift.",
       "organization_id": 42, "updated_at": "2026-03-14T09:00:00Z",
       "tags": ["allocation"], "requester_id": 5}
COMMENTS = [{"author_id": 9, "public": True,
             "body": "Replenishment lagged behind demand; reran it and the wave allocated.",
             "created_at": "2026-03-14T10:00:00Z"}]


def test_dry_run_never_calls_the_model_or_writes(tmp_path):
    llm = FakeLLM()
    report = ingest(clients=["alpha"], org_ids={"alpha": [42]},
                    connector=FakeConnector([ROW], COMMENTS), llm=llm,
                    clients_dir=tmp_path / "clients", concepts_dir=tmp_path / "concepts",
                    state_dir=tmp_path / "state", dry_run=True)
    assert report.fetched == 1
    assert llm.calls == 0
    assert not (tmp_path / "clients").exists()


def test_real_run_emits_a_card(tmp_path):
    (tmp_path / "concepts").mkdir()
    report = ingest(clients=["alpha"], org_ids={"alpha": [42]},
                    connector=FakeConnector([ROW], COMMENTS), llm=FakeLLM(),
                    clients_dir=tmp_path / "clients", concepts_dir=tmp_path / "concepts",
                    state_dir=tmp_path / "state")
    assert report.emitted == 1
    written = list((tmp_path / "clients" / "alpha" / "issues").glob("*.md"))
    assert len(written) == 1 and written[0].name.startswith("14872-")


def test_emitted_card_is_stamped_with_the_installed_version(tmp_path):
    """`distilled_by` is provenance committed to the corpus, so it must name the version the
    operator actually installed - a hand-kept literal drifts from the released one silently."""
    installed = metadata.version("vf-hive-zendesk")
    assert hivezendesk.__version__ == installed

    (tmp_path / "concepts").mkdir()
    ingest(clients=["alpha"], org_ids={"alpha": [42]},
           connector=FakeConnector([ROW], COMMENTS), llm=FakeLLM(),
           clients_dir=tmp_path / "clients", concepts_dir=tmp_path / "concepts",
           state_dir=tmp_path / "state")
    written = list((tmp_path / "clients" / "alpha" / "issues").glob("*.md"))
    assert len(written) == 1
    fm = parse_frontmatter(written[0].read_text())
    assert fm["distilled_by"] == f"hive-zendesk@{installed}"


def test_run_records_skip_reasons(tmp_path):
    (tmp_path / "concepts").mkdir()
    noise = dict(ROW, id=99, subject="Password reset request",
                 description="Please reset my password for the portal now.")
    report = ingest(clients=["alpha"], org_ids={"alpha": [42]},
                    connector=FakeConnector([noise], COMMENTS), llm=FakeLLM(),
                    clients_dir=tmp_path / "clients", concepts_dir=tmp_path / "concepts",
                    state_dir=tmp_path / "state")
    assert report.emitted == 0 and report.skipped == 1
    assert report.skipped_reasons == [(99, "noise-pattern")]


def test_second_run_is_idempotent(tmp_path):
    (tmp_path / "concepts").mkdir()
    kw = {"clients": ["alpha"], "org_ids": {"alpha": [42]},
              "connector": FakeConnector([ROW], COMMENTS), "llm": FakeLLM(),
              "clients_dir": tmp_path / "clients", "concepts_dir": tmp_path / "concepts",
              "state_dir": tmp_path / "state"}
    ingest(**kw)
    ingest(**kw)
    written = list((tmp_path / "clients" / "alpha" / "issues").glob("*.md"))
    assert len(written) == 1


class PIILLM(FakeLLM):
    def complete(self, system, user):
        self.calls += 1
        return json.dumps({"what_happened": "call +1 555 555 0100 to confirm",
                           "how_it_closed": "", "module": "allocation", "tags": [],
                           "related_candidates": [], "routine": False})


def test_pii_is_quarantined_not_aborted(tmp_path):
    """One leaky card must not kill a several-hundred-ticket backfill."""
    (tmp_path / "concepts").mkdir()
    report = ingest(clients=["alpha"], org_ids={"alpha": [42]},
                    connector=FakeConnector([ROW], COMMENTS), llm=PIILLM(),
                    clients_dir=tmp_path / "clients", concepts_dir=tmp_path / "concepts",
                    state_dir=tmp_path / "state")
    assert report.pii_held == 1 and report.emitted == 0
    tid, kinds = report.pii_tickets[0]
    assert tid == 14872 and "phone" in kinds
    assert "555" not in str(report.pii_tickets)          # kinds only, never the value
    assert not list((tmp_path / "clients" / "alpha" / "issues").glob("*.md"))


def test_already_carded_ticket_is_not_refetched_or_redistilled(tmp_path):
    """Closed tickets are immutable: a replayed window must not re-spend on them."""
    (tmp_path / "concepts").mkdir()
    kw = {"clients": ["alpha"], "org_ids": {"alpha": [42]},
              "clients_dir": tmp_path / "clients", "concepts_dir": tmp_path / "concepts",
              "state_dir": tmp_path / "state"}
    first = FakeLLM()
    ingest(connector=FakeConnector([ROW], COMMENTS), llm=first, **kw)
    assert first.calls == 1

    second = FakeLLM()
    report = ingest(connector=FakeConnector([ROW], COMMENTS), llm=second, **kw)
    assert second.calls == 0          # no LLM spend on a ticket already carded
    assert report.cached == 1 and report.emitted == 0


def test_one_bad_ticket_does_not_kill_the_run(tmp_path):
    (tmp_path / "concepts").mkdir()

    class Exploding(FakeConnector):
        def get_ticket(self, ticket_id):
            if ticket_id == 999:
                raise RuntimeError("connector blew up")
            return {"comments": self.comments}

    other = dict(ROW, id=999)
    report = ingest(clients=["alpha"], org_ids={"alpha": [42]},
                    connector=Exploding([ROW, other], COMMENTS), llm=FakeLLM(),
                    clients_dir=tmp_path / "clients", concepts_dir=tmp_path / "concepts",
                    state_dir=tmp_path / "state")
    assert report.emitted == 1 and report.failed == 1
    assert report.failures[0][0] == 999


def test_limit_samples_without_breaking_reconciliation(tmp_path):
    """--limit is how a backfill gets sized; it must not trip the counts gate."""
    (tmp_path / "concepts").mkdir()
    # distinct subjects: identical tickets would (correctly) be dropped as duplicates
    rows = [dict(ROW, id=1000 + i, subject=f"Distinct issue {i}") for i in range(5)]
    report = ingest(clients=["alpha"], org_ids={"alpha": [42]},
                    connector=FakeConnector(rows, COMMENTS), llm=FakeLLM(),
                    clients_dir=tmp_path / "clients", concepts_dir=tmp_path / "concepts",
                    state_dir=tmp_path / "state", dry_run=True, limit=2)
    assert report.fetched == 2 and report.emitted == 2


def test_rebuild_refuses_without_a_bucket(monkeypatch, tmp_path, capsys):
    """`rebuild` reads staged cards off R2. Unset must stop it, naming the setting, rather
    than reaching boto3 and failing four frames down on an empty endpoint."""
    import hivezendesk.run

    monkeypatch.chdir(tmp_path)  # no .env of the developer's own
    for key in ("R2_BUCKET", "R2_ENDPOINT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BIFROST_BASE", "http://bf/v1")
    monkeypatch.setenv("BIFROST_API_KEY", "k")
    monkeypatch.setattr("sys.argv", [
        "hivezendesk", "rebuild", "--client", "alpha",
        "--clients-dir", str(tmp_path / "clients"), "--concepts-dir", str(tmp_path / "concepts"),
    ])

    with pytest.raises(SystemExit):
        hivezendesk.run.main()
    assert "R2_BUCKET" in capsys.readouterr().err


def test_rebuild_refuses_without_an_endpoint(monkeypatch, tmp_path, capsys):
    """A bucket is not enough. An empty endpoint_url is rejected too, but by botocore and as
    `ValueError: Invalid endpoint:` several frames down, naming no setting - which is the
    failure this refusal replaces."""
    import hivezendesk.run

    monkeypatch.chdir(tmp_path)  # no .env of the developer's own
    monkeypatch.setenv("R2_BUCKET", "some-bucket")
    monkeypatch.delenv("R2_ENDPOINT", raising=False)
    monkeypatch.setenv("BIFROST_BASE", "http://bf/v1")
    monkeypatch.setenv("BIFROST_API_KEY", "k")
    monkeypatch.setattr("sys.argv", [
        "hivezendesk", "rebuild", "--client", "alpha",
        "--clients-dir", str(tmp_path / "clients"), "--concepts-dir", str(tmp_path / "concepts"),
    ])

    with pytest.raises(SystemExit):
        hivezendesk.run.main()
    assert "R2_ENDPOINT" in capsys.readouterr().err

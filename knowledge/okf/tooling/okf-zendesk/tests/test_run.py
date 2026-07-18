import json

from okfzendesk.run import ingest


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
        return json.dumps({"title": "Wave allocation stalls", "description": "d",
                           "module": "allocation", "tags": ["allocation"],
                           "related_candidates": [], "symptom": "s",
                           "diagnosis": "dg", "resolution": "r", "context": "c"})


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
    kw = dict(clients=["alpha"], org_ids={"alpha": [42]},
              connector=FakeConnector([ROW], COMMENTS), llm=FakeLLM(),
              clients_dir=tmp_path / "clients", concepts_dir=tmp_path / "concepts",
              state_dir=tmp_path / "state")
    ingest(**kw)
    ingest(**kw)
    written = list((tmp_path / "clients" / "alpha" / "issues").glob("*.md"))
    assert len(written) == 1

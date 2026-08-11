import pytest

from hiveauthor.issue_client import FakeIssueClient, ForgejoIssueClient, UnknownLabelError


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def _patch(monkeypatch, captured, labels_payload):
    def fake_get(url, headers=None, timeout=None, params=None):
        captured["get_url"] = url
        return _Resp(labels_payload)

    def fake_post(url, headers=None, timeout=None, json=None):
        captured.update(url=url, headers=headers, json=json)
        return _Resp({"number": 7, "html_url": "https://forge.test/7"})

    monkeypatch.setattr("hiveauthor.issue_client.httpx.get", fake_get)
    monkeypatch.setattr("hiveauthor.issue_client.httpx.post", fake_post)


def test_fake_records_and_returns():
    gh = FakeIssueClient()
    out = gh.create_issue(title="t", body="b", labels=["hive-memory"])
    assert out["number"] == 1 and gh.calls[0]["labels"] == ["hive-memory"]


def test_label_names_are_resolved_to_ids(monkeypatch):
    """Forgejo takes label IDs, not names. Sending names is a 422."""
    captured = {}
    _patch(monkeypatch, captured, [{"name": "hive-correction", "id": 42},
                                   {"name": "hive-memory", "id": 41}])
    gh = ForgejoIssueClient("http://forge/api/v1", "example/corpus", "tok")
    out = gh.create_issue(title="t", body="b", labels=["hive-correction"])

    assert out == {"number": 7, "url": "https://forge.test/7"}
    assert captured["url"] == "http://forge/api/v1/repos/example/corpus/issues"
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert captured["json"] == {"title": "t", "body": "b", "labels": [42]}


def test_unknown_label_raises_rather_than_dropping(monkeypatch):
    """A dropped label files an issue the corpus workflows never select. Fail instead."""
    captured = {}
    _patch(monkeypatch, captured, [{"name": "hive-memory", "id": 41}])
    gh = ForgejoIssueClient("http://forge/api/v1", "example/corpus", "tok")
    with pytest.raises(UnknownLabelError, match="hive-correction"):
        gh.create_issue(title="t", body="b", labels=["hive-correction"])
    assert "url" not in captured, "no issue should be created when a label is unknown"


def test_label_lookup_is_cached(monkeypatch):
    captured = {}
    calls = {"n": 0}
    _patch(monkeypatch, captured, [{"name": "hive-memory", "id": 41}])
    real_get = __import__("hiveauthor.issue_client", fromlist=["httpx"]).httpx.get

    def counting_get(*a, **k):
        calls["n"] += 1
        return real_get(*a, **k)

    monkeypatch.setattr("hiveauthor.issue_client.httpx.get", counting_get)
    gh = ForgejoIssueClient("http://forge/api/v1", "example/corpus", "tok")
    gh.create_issue(title="t", body="b", labels=["hive-memory"])
    gh.create_issue(title="t2", body="b", labels=["hive-memory"])
    assert calls["n"] == 1


def test_no_labels_skips_lookup_entirely(monkeypatch):
    captured = {}
    _patch(monkeypatch, captured, [])
    gh = ForgejoIssueClient("http://forge/api/v1", "example/corpus", "tok")
    gh.create_issue(title="t", body="b", labels=[])
    assert captured["json"]["labels"] == []
    assert "get_url" not in captured

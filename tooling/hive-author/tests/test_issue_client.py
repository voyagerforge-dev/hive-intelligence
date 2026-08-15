import pytest

from hiveauthor.issue_client import (
    FakeIssueClient,
    ForgejoIssueClient,
    GitHubIssueClient,
    UnknownLabelError,
)


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


# ---------------------------------------------------------------------------
# GitHub. EXAMPLECO returned to github.com/example-org on 2026-08-15, so the same server
# has to file issues on either forge depending on the deployment.
# ---------------------------------------------------------------------------

def test_github_sends_label_names_not_ids(monkeypatch):
    """The whole reason there are two clients: GitHub takes names, Forgejo takes ints."""
    captured = {}
    _patch(monkeypatch, captured, [{"name": "hive-memory", "id": 41}])
    gh = GitHubIssueClient("https://api.github.com", "example-org/corpus", "tok")
    out = gh.create_issue(title="t", body="b", labels=["hive-memory"])

    assert out == {"number": 7, "url": "https://forge.test/7"}
    assert captured["url"] == "https://api.github.com/repos/example-org/corpus/issues"
    assert captured["json"] == {"title": "t", "body": "b", "labels": ["hive-memory"]}


def test_github_also_refuses_an_unknown_label(monkeypatch):
    """GitHub would auto-create the label rather than drop it, so this is not about
    losing the label. It is so that a deployment moving between forges does not
    silently change what a typo does: on both, a bad label fails the submission
    instead of quietly creating something nobody meant."""
    captured = {}
    _patch(monkeypatch, captured, [{"name": "hive-memory", "id": 41}])
    gh = GitHubIssueClient("https://api.github.com", "example-org/corpus", "tok")
    with pytest.raises(UnknownLabelError, match="hive-correction"):
        gh.create_issue(title="t", body="b", labels=["hive-correction"])
    assert "url" not in captured


def test_a_callable_token_is_read_on_every_call(monkeypatch):
    """App installation tokens last an hour and this process outlives that.

    A token captured at construction is the failure that matters: it works all
    afternoon and then 401s, in a service whose whole job is to file something a
    consultant has already typed.
    """
    captured = {}
    _patch(monkeypatch, captured, [{"name": "hive-memory", "id": 41}])
    tokens = iter(["first", "second"])
    gh = GitHubIssueClient("https://api.github.com", "example-org/corpus",
                           lambda: next(tokens))

    gh.create_issue(title="t", body="b", labels=[])
    assert captured["headers"]["Authorization"] == "Bearer first"
    gh.create_issue(title="t", body="b", labels=[])
    assert captured["headers"]["Authorization"] == "Bearer second"


def test_forgejo_accepts_a_callable_token_too(monkeypatch):
    captured = {}
    _patch(monkeypatch, captured, [{"name": "hive-memory", "id": 41}])
    gh = ForgejoIssueClient("http://forge/api/v1", "example/corpus", lambda: "rotated")
    gh.create_issue(title="t", body="b", labels=[])
    assert captured["headers"]["Authorization"] == "Bearer rotated"

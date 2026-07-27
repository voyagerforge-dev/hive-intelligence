from hiveauthor.github_client import FakeIssueClient, GitHubIssueClient


def test_fake_records_and_returns():
    gh = FakeIssueClient()
    out = gh.create_issue(title="t", body="b", labels=["okf-memory"])
    assert out["number"] == 1 and gh.calls[0]["labels"] == ["okf-memory"]


def test_github_client_posts_expected_payload(monkeypatch):
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"number": 7, "html_url": "https://github.test/7"}

    def fake_post(url, headers=None, timeout=None, json=None):
        captured.update(url=url, headers=headers, json=json)
        return _Resp()

    monkeypatch.setattr("hiveauthor.github_client.httpx.post", fake_post)
    gh = GitHubIssueClient("https://api.github.com", "org/repo", "tok")
    out = gh.create_issue(title="t", body="b", labels=["okf-correction"])
    assert out == {"number": 7, "url": "https://github.test/7"}
    assert captured["url"] == "https://api.github.com/repos/org/repo/issues"
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert captured["json"] == {"title": "t", "body": "b", "labels": ["okf-correction"]}

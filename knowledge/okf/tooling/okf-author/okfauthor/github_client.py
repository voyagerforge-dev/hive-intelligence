"""Injectable GitHub issue client. The real client needs only issues:write; tests use the fake."""
from __future__ import annotations

from typing import Protocol

import httpx


class IssueClient(Protocol):
    def create_issue(self, *, title: str, body: str, labels: list[str]) -> dict: ...


class FakeIssueClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create_issue(self, *, title, body, labels) -> dict:
        self.calls.append({"title": title, "body": body, "labels": labels})
        n = len(self.calls)
        return {"number": n, "url": f"https://github.test/issues/{n}"}


class GitHubIssueClient:
    def __init__(self, api: str, repo: str, token: str, timeout_s: int = 30) -> None:
        self._url = f"{api}/repos/{repo}/issues"
        self._headers = {"Authorization": f"Bearer {token}",
                         "Accept": "application/vnd.github+json"}
        self._timeout = timeout_s

    def create_issue(self, *, title, body, labels) -> dict:
        r = httpx.post(self._url, headers=self._headers, timeout=self._timeout,
                       json={"title": title, "body": body, "labels": labels})
        r.raise_for_status()
        d = r.json()
        return {"number": d["number"], "url": d["html_url"]}

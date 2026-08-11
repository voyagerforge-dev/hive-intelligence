"""Injectable forge issue client. The real client needs only issue:write; tests use the fake."""
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
        return {"number": n, "url": f"https://forge.test/issues/{n}"}


class UnknownLabelError(RuntimeError):
    """A requested label does not exist on the target repository."""


class ForgejoIssueClient:
    """Creates issues on a Forgejo forge.

    Forgejo's issue API is GitHub-shaped except in one place that matters: `labels` takes
    integer label IDs, where GitHub takes names. Posting names gets a 422 reading
    `cannot unmarshal string into Go struct field CreateIssueOption.labels of type int64`.

    So this resolves names to IDs first. The resolution is strict on purpose. Silently
    dropping a label nobody recognises would still create the issue and still report
    success, while the corpus workflows that select on `hive-memory` would never see it,
    and the submission would look filed and be invisible. Better to fail the submission.
    """

    def __init__(self, api: str, repo: str, token: str, timeout_s: int = 30) -> None:
        self._base = f"{api}/repos/{repo}"
        self._url = f"{self._base}/issues"
        # Forgejo accepts the Bearer scheme as well as `token <sha1>`; Bearer is kept so
        # the header shape is unchanged from the GitHub client this replaces.
        self._headers = {"Authorization": f"Bearer {token}",
                         "Accept": "application/json"}
        self._timeout = timeout_s
        self._label_ids: dict[str, int] | None = None

    def _labels_by_name(self) -> dict[str, int]:
        if self._label_ids is None:
            r = httpx.get(f"{self._base}/labels", headers=self._headers,
                          timeout=self._timeout, params={"limit": 100})
            r.raise_for_status()
            self._label_ids = {lab["name"]: lab["id"] for lab in r.json()}
        return self._label_ids

    def create_issue(self, *, title, body, labels) -> dict:
        ids: list[int] = []
        if labels:
            known = self._labels_by_name()
            missing = [n for n in labels if n not in known]
            if missing:
                raise UnknownLabelError(
                    f"labels absent on {self._base}: {', '.join(missing)}. "
                    "Create them on the repository; do not drop them."
                )
            ids = [known[n] for n in labels]
        r = httpx.post(self._url, headers=self._headers, timeout=self._timeout,
                       json={"title": title, "body": body, "labels": ids})
        r.raise_for_status()
        d = r.json()
        return {"number": d["number"], "url": d["html_url"]}

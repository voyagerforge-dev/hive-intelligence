"""Injectable forge issue client. The real client needs only issue:write; tests use the fake."""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import httpx

# A token, or something that produces one. Callables exist because a GitHub App
# installation token lasts an hour while this server runs for days: a token captured at
# construction works all afternoon and then 401s, in a service whose only job is to file
# something a consultant has already typed. Resolved per request, never cached.
TokenSource = str | Callable[[], str]


def _token(src: TokenSource) -> str:
    return src() if callable(src) else src


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

    def __init__(self, api: str, repo: str, token: TokenSource, timeout_s: int = 30) -> None:
        self._base = f"{api}/repos/{repo}"
        self._url = f"{self._base}/issues"
        self._token = token
        self._timeout = timeout_s
        self._label_ids: dict[str, int] | None = None

    # Forgejo accepts the Bearer scheme as well as `token <sha1>`; Bearer is kept so the
    # header shape matches the GitHub client beside it. Built per call rather than stored,
    # so a rotating token is picked up.
    def _hdrs(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {_token(self._token)}",
                "Accept": "application/json"}

    def _labels_by_name(self) -> dict[str, int]:
        if self._label_ids is None:
            r = httpx.get(f"{self._base}/labels", headers=self._hdrs(),
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
        r = httpx.post(self._url, headers=self._hdrs(), timeout=self._timeout,
                       json={"title": title, "body": body, "labels": ids})
        r.raise_for_status()
        d = r.json()
        return {"number": d["number"], "url": d["html_url"]}


class GitHubIssueClient:
    """Creates issues on github.com.

    Both clients are kept because a corpus repository legitimately moves between forges, and
    has: a deployment picks one with FORGE_KIND, and neither client is a fork of the other.

    The difference that forces two classes is one field. GitHub's `labels` takes names;
    Forgejo's takes integer IDs and answers a name with 422.

    Unknown labels are still refused here, even though GitHub would create one rather
    than drop it. That is not about losing the label, it is so that moving a deployment
    between forges does not silently change what a typo does. On both, a bad label fails
    the submission rather than quietly creating something nobody meant.
    """

    def __init__(self, api: str, repo: str, token: TokenSource, timeout_s: int = 30) -> None:
        self._base = f"{api}/repos/{repo}"
        self._url = f"{self._base}/issues"
        self._token = token
        self._timeout = timeout_s
        self._label_names: set[str] | None = None

    def _hdrs(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {_token(self._token)}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"}

    def _known_labels(self) -> set[str]:
        if self._label_names is None:
            r = httpx.get(f"{self._base}/labels", headers=self._hdrs(),
                          timeout=self._timeout, params={"per_page": 100})
            r.raise_for_status()
            self._label_names = {lab["name"] for lab in r.json()}
        return self._label_names

    def create_issue(self, *, title, body, labels) -> dict:
        if labels:
            missing = [n for n in labels if n not in self._known_labels()]
            if missing:
                raise UnknownLabelError(
                    f"labels absent on {self._base}: {', '.join(missing)}. "
                    "Create them on the repository; do not drop them."
                )
        r = httpx.post(self._url, headers=self._hdrs(), timeout=self._timeout,
                       json={"title": title, "body": body, "labels": list(labels)})
        r.raise_for_status()
        d = r.json()
        return {"number": d["number"], "url": d["html_url"]}

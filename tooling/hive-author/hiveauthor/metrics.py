"""Prometheus metrics for hive-author, the write door.

Mirrors hive-serve's module deliberately: same registry-per-service shape, same
naming, so the two dashboards read alike.

What is counted is chosen to answer the question this service actually raises,
which is not "is it up". A write door can be up, healthy, accepting requests and
filing nothing, because the token lost its repository grant or the label names
drifted. Both have happened. So the counter is keyed on **outcome**, not just on
calls:

    filed          the issue exists on the forge, with a number
    rejected       the submission failed validation before any API call
    github_error   the forge refused it

The `github_error` label value predates support for a second forge kind and means
"the forge refused it" whichever forge that is. It is kept because a label value is
a public interface: any alert rule or dashboard built on it breaks silently when it
is renamed, for cosmetic gain. Rename it everywhere it is consumed, or not at all.

`rejected` and `github_error` are separated on purpose. The first is a user
getting it wrong and is not a fault. The second is ours, and is the one worth
alerting on: a 404 from the forge means a token that cannot see the repository,
which reads identically to a wrong URL.
"""
from __future__ import annotations

import time
from contextlib import contextmanager

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry()

SUBMISSIONS = Counter(
    "hive_author_submissions_total",
    "hive-author write-tool submissions by tool and outcome",
    ["tool", "outcome"], registry=REGISTRY)

SUBMISSION_LATENCY = Histogram(
    "hive_author_submission_duration_seconds",
    "hive-author write-tool duration, including the GitHub API call",
    ["tool"], registry=REGISTRY)


def render():
    """The /metrics body and content type."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


@contextmanager
def record(tool: str):
    """Time a submission and record its outcome.

    Yields a one-element list; set `out[0]` to the outcome. Defaults to
    `github_error`, so an exception escaping the block is counted as a failure
    rather than silently not counted at all. A metric that only increments on
    success cannot show you an outage.
    """
    out = ["github_error"]
    start = time.perf_counter()
    try:
        yield out
    finally:
        SUBMISSION_LATENCY.labels(tool=tool).observe(time.perf_counter() - start)
        SUBMISSIONS.labels(tool=tool, outcome=out[0]).inc()

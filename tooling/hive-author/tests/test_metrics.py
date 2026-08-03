"""The write door's metrics, which exist to answer 'is it filing', not 'is it up'."""
from prometheus_client.parser import text_string_to_metric_families

from hiveauthor import metrics


def _families():
    body, _ = metrics.render()
    return {f.name: f for f in text_string_to_metric_families(body.decode())}


def test_outcome_defaults_to_failure_when_the_block_raises():
    """An exception escaping must count as github_error, not vanish.

    A counter that only increments on success cannot show an outage: the graph
    goes flat and flat reads the same as idle.
    """
    before = _count("submit_correction", "github_error")
    try:
        with metrics.record("submit_correction"):
            raise RuntimeError("GitHub 404")
    except RuntimeError:
        pass
    assert _count("submit_correction", "github_error") == before + 1


def test_rejected_and_github_error_are_distinguished():
    """A user getting it wrong is not a fault; a token that cannot see the repo is.

    Collapsing the two would make the alert either useless or permanently firing.
    """
    with metrics.record("submit_memory_promotion") as out:
        out[0] = "rejected"
    with metrics.record("submit_memory_promotion") as out:
        out[0] = "filed"
    assert _count("submit_memory_promotion", "rejected") >= 1
    assert _count("submit_memory_promotion", "filed") >= 1


def test_latency_is_observed_per_tool():
    with metrics.record("submit_correction") as out:
        out[0] = "filed"
    fams = _families()
    assert "hive_author_submission_duration_seconds" in fams
    tools = {s.labels.get("tool") for s in fams["hive_author_submission_duration_seconds"].samples}
    assert "submit_correction" in tools


def _count(tool, outcome):
    fams = _families()
    f = fams.get("hive_author_submissions")
    if not f:
        return 0
    for s in f.samples:
        if s.labels.get("tool") == tool and s.labels.get("outcome") == outcome and s.name.endswith("_total"):
            return s.value
    return 0

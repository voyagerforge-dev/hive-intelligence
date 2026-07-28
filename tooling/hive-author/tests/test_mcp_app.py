import anyio

from hiveauthor.config import Settings
from hiveauthor.github_client import FakeIssueClient
from hiveauthor.mcp_app import build_mcp
from hiveauthor.submissions import build_correction_submission, build_memory_submission


def test_tools_registered():
    mcp = build_mcp(Settings(), lambda: FakeIssueClient())
    names = {t.name for t in anyio.run(mcp.list_tools)}
    assert {"submit_memory_promotion", "submit_correction"} <= names


def test_hard_separation_of_build_helpers():
    # memory always labels okf-memory + needs a client; correction always labels okf-correction
    m = build_memory_submission(owner="o", client="alpha", product="widgets", title="t", lesson="l")
    c = build_correction_submission(owner="o", target_concept_id="widgets/x",
                                    corrected_fact="f", rationale="r")
    assert m["labels"] == ["okf-memory"] and c["labels"] == ["okf-correction"]
    assert "Client" in m["body"] and "Target concept id" in c["body"]
    assert "Client" not in c["body"] and "Target concept id" not in m["body"]

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hivegen.scripts import memory_lint
from hivegen.scripts import pr_conflict_gate as pcg

# tests -> hive-gen -> tooling -> repo root. hive-intelligence ships no corpus of its own
# (the corpus lives with whichever product repository consumes this tooling), but the
# hive-serve fixtures give us a real, on-disk `clients/` tree to anchor against instead of
# a path this test would otherwise have to invent.
_FIXTURE_CORPUS = Path(__file__).resolve().parents[3] / "tooling" / "hive-serve" / "tests" / "fixtures" / "corpus"


class FakeLLM:
    def __init__(self, prob):
        self._p = prob

    def complete(self, system, user):
        return f'{{"probability": {self._p}, "rationale": "x"}}'


def test_pr_touches_memory():
    assert pcg.pr_touches_memory(["clients/alpha/memory/x.md"]) is True
    assert pcg.pr_touches_memory(["clients/widgets/a.md"]) is False
    assert pcg.pr_touches_memory(["concepts/wms/a.md"]) is False
    assert pcg.pr_touches_memory(["README.md"]) is False


@pytest.mark.skipif(
    not (_FIXTURE_CORPUS / "clients").is_dir(),
    reason="no fixture corpus on disk to anchor against",
)
def test_the_gate_matches_a_memory_card_that_actually_exists():
    """Anchored to a real corpus tree, not to a path this test made up.

    A version of this test written against `knowledge/okf/clients/alpha/memory/x.md`
    would pass forever while the gate matched nothing real, because the test and the code
    would share the same wrong assumption. A test that invents its own input cannot catch
    that; one that reads an actual tree can. hive-intelligence carries no corpus of its
    own, so this reads the hive-serve fixture corpus instead of a repo-root `clients/`.
    """
    cards = [p for p in (_FIXTURE_CORPUS / "clients").glob("*/memory/*.md") if p.name != "index.md"]
    assert cards, "no client memory cards found in the fixture corpus; this test has lost track of it"
    rel = [str(p.relative_to(_FIXTURE_CORPUS)) for p in cards]
    assert pcg.pr_touches_memory(rel) is True, f"the gate does not recognise {rel[0]}"


def test_the_gate_and_the_linter_agree_on_where_memory_lives():
    """One fact, one string. Their disagreement is what made the gate inert.

    `memory_lint` builds card ids from this prefix and the gate decides what to score by
    it. If they ever diverge again, a PR can change a card the linter knows about and the
    gate will wave it through.
    """
    assert pcg.pr_touches_memory([f"{memory_lint.CLIENTS_PREFIX}acme/memory/a.md"]) is True


def test_verdict_to_status():
    b = pcg.verdict_to_status([("clients/alpha/memory/a", "clients/alpha/memory/b")], [])
    assert b["state"] == "failure" and "a <> " in b["description"] and b["context"] == "okf/memory-conflict"
    r = pcg.verdict_to_status([], [("clients/alpha/memory/c", "clients/alpha/memory/d")])
    assert r["state"] == "failure"
    ok = pcg.verdict_to_status([], [])
    assert ok["state"] == "success"


def _tree(tmp_path):
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    (concepts / "widgets").mkdir(parents=True)
    (concepts / "widgets" / "alloc.md").write_text("---\ntitle: A\ntype: concept\n---\n\nbody\n")
    md = clients / "alpha" / "memory"
    md.mkdir(parents=True)
    for s in ("m1", "m2"):
        (md / f"{s}.md").write_text(
            "---\ntype: memory\nclient: alpha\nproduct: widgets\nstatus: approved\n"
            "related: [widgets/alloc]\n---\n\n## Memory\n\n" + s + " note\n")
    return concepts, clients


def test_score_tree_blocks_on_high_prob(tmp_path):
    concepts, clients = _tree(tmp_path)
    blocking, review = pcg.score_tree(clients, concepts, FakeLLM(0.9))
    assert blocking and not review


def test_score_tree_clears_on_low_prob(tmp_path):
    concepts, clients = _tree(tmp_path)
    blocking, review = pcg.score_tree(clients, concepts, FakeLLM(0.1))
    assert not blocking and not review


def _run_gate(*args: str) -> subprocess.CompletedProcess:
    """The command as a caller actually gets it, with the stdin CI hands a `run:` step.

    A GitHub Actions step gets /dev/null on stdin, so this is the shape in which the gate
    used to answer `state: success` over a pull request it had never been told anything
    about. The gateway credentials are stripped so no test can reach a network.
    """
    env = {k: v for k, v in os.environ.items()
           if k not in ("BIFROST_BASE", "BIFROST_API_KEY")}
    return subprocess.run(
        [sys.executable, "-m", "hivegen.scripts.pr_conflict_gate", *args],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env, check=False,
    )


def test_main_refuses_a_changeset_nobody_supplied(tmp_path):
    """No changed files named is not a verdict, and must never print one."""
    concepts, clients = _tree(tmp_path)
    r = _run_gate(str(clients), str(concepts))
    assert r.returncode != 0, f"the gate exited 0 without being given a changeset: {r.stdout!r}"
    assert "success" not in r.stdout
    assert "no changed files were supplied" in r.stderr.lower()


def test_main_clears_a_supplied_changeset_that_touches_no_memory(tmp_path):
    concepts, clients = _tree(tmp_path)
    r = _run_gate(str(clients), str(concepts),
                  "--changed-file", "README.md",
                  "--changed-file", "concepts/widgets/alloc.md")
    assert r.returncode == 0, r.stderr
    status = json.loads(r.stdout)
    assert status["context"] == "okf/memory-conflict"
    assert status["state"] == "success"


def test_main_refuses_to_score_a_memory_change_without_a_gateway(tmp_path):
    """The changeset was supplied and does touch memory, so a verdict needs real scoring."""
    concepts, clients = _tree(tmp_path)
    r = _run_gate(str(clients), str(concepts),
                  "--changed-file", f"{memory_lint.CLIENTS_PREFIX}alpha/memory/m1.md")
    assert r.returncode != 0
    assert "success" not in r.stdout
    assert "BIFROST_BASE" in r.stderr

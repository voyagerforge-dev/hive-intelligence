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


def _run_gate(*args: str, cwd, gateway: bool = False) -> subprocess.CompletedProcess:
    """The command as a caller actually gets it, with the stdin CI hands a `run:` step.

    A GitHub Actions step gets /dev/null on stdin, so this is the shape in which the gate
    used to answer `state: success` over a pull request it had never been told anything
    about. `cwd` is load-bearing: the gate matches `--changed-file` values against
    `clients_dir` relative to where it runs, so these run from the tree's own root the way
    a workflow runs from the repository root. The gateway credentials are stripped so no
    test can reach a network; `gateway=True` puts back the pair of variables the gate
    checks for, pointed at the loopback discard port, for the cases whose failure lies
    PAST that check and would otherwise be hidden by it.
    """
    env = {k: v for k, v in os.environ.items()
           if k not in ("BIFROST_BASE", "BIFROST_API_KEY")}
    if gateway:
        env["BIFROST_BASE"] = "http://127.0.0.1:9/v1"
        env["BIFROST_API_KEY"] = "not-a-key"
    return subprocess.run(
        [sys.executable, "-m", "hivegen.scripts.pr_conflict_gate", *args],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env, check=False,
        cwd=str(cwd),
    )


def test_main_refuses_a_changeset_nobody_supplied(tmp_path):
    """No changed files named is not a verdict, and must never print one."""
    _tree(tmp_path)
    r = _run_gate("clients", "concepts", cwd=tmp_path)
    assert r.returncode != 0, f"the gate exited 0 without being given a changeset: {r.stdout!r}"
    assert "success" not in r.stdout
    assert "no changed files were supplied" in r.stderr.lower()


def test_main_clears_a_supplied_changeset_that_touches_no_memory(tmp_path):
    _tree(tmp_path)
    r = _run_gate("clients", "concepts",
                  "--changed-file", "README.md",
                  "--changed-file", "concepts/widgets/alloc.md", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    status = json.loads(r.stdout)
    assert status["context"] == "okf/memory-conflict"
    assert status["state"] == "success"


def test_main_refuses_to_score_a_memory_change_without_a_gateway(tmp_path):
    """The changeset was supplied and does touch memory, so a verdict needs real scoring."""
    _tree(tmp_path)
    r = _run_gate("clients", "concepts",
                  "--changed-file", "clients/alpha/memory/m1.md", cwd=tmp_path)
    assert r.returncode != 0
    assert "success" not in r.stdout
    assert "BIFROST_BASE" in r.stderr


def test_main_sees_a_memory_change_in_a_corpus_below_the_repository_root(tmp_path):
    """The changed path and the clients tree agree; only the `clients/` literal did not.

    A gate that reports green because its hardcoded prefix missed the corpus layout is the
    exact failure `pr_touches_memory`'s docstring exists over: the green is evidence of
    nothing and reads as evidence of something. Reaching the gateway refusal is what proves
    the card was recognised.
    """
    _tree(tmp_path / "corpus")
    r = _run_gate("corpus/clients", "corpus/concepts",
                  "--changed-file", "corpus/clients/alpha/memory/m1.md", cwd=tmp_path)
    assert "success" not in r.stdout, f"the gate waved through a memory change: {r.stdout!r}"
    assert r.returncode != 0
    assert "BIFROST_BASE" in r.stderr


def test_main_still_clears_a_non_memory_change_in_a_corpus_below_the_root(tmp_path):
    """Deriving the prefix must not turn every nested-corpus PR into a refusal."""
    _tree(tmp_path / "corpus")
    r = _run_gate("corpus/clients", "corpus/concepts",
                  "--changed-file", "corpus/concepts/widgets/alloc.md", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["state"] == "success"


def test_main_refuses_a_clients_dir_that_is_not_the_tree_the_changed_card_lives_in(tmp_path):
    """One level too high is a tree holding no memory card, and that scores zero conflicts.

    `require_dir` accepts it because it is a directory, and `changed_path_prefix` accepts it
    because it is neither outside the working directory nor equal to it, so the derived
    prefix matches the changed card and the gate proceeds to score. `memory_lint` then finds
    nothing under it, because the ids it builds need a client directory directly above
    `memory/`, and zero cards read as zero conflicts. The gateway is configured so that
    green is reachable at all: without it the gate stops at the gateway refusal first and
    the green stays hidden. `test_main_sees_a_memory_change_in_a_corpus_below_the_repository
    _root` is the same layout named at the right level, and still reaches real scoring.
    """
    _tree(tmp_path / "corpus")
    r = _run_gate("corpus", "corpus/concepts",
                  "--changed-file", "corpus/clients/alpha/memory/m1.md",
                  cwd=tmp_path, gateway=True)
    assert "success" not in r.stdout, f"the gate answered over a tree with no card in it: {r.stdout!r}"
    assert r.returncode != 0
    assert "clients_dir=corpus holds no client memory card" in r.stderr


def test_main_clears_a_memory_change_whose_cards_share_no_subject(tmp_path):
    """Zero candidate PAIRS is the healthy outcome and must not be read as zero cards.

    This is where most memory pull requests land: the tree holds cards, none of them
    overlap, and the gate publishes a green it is entitled to. The refusal above triggers
    on an empty TREE; triggering it on an empty scoring result instead would block nearly
    every legitimate memory change. Nothing is sent to the gateway, because a single card
    pairs with nothing and the scorer is never reached.
    """
    concepts = tmp_path / "concepts" / "widgets"
    concepts.mkdir(parents=True)
    (concepts / "alloc.md").write_text("---\ntitle: A\ntype: concept\n---\n\nbody\n")
    md = tmp_path / "clients" / "alpha" / "memory"
    md.mkdir(parents=True)
    (md / "m1.md").write_text(
        "---\ntype: memory\nclient: alpha\nproduct: widgets\nstatus: approved\n"
        "related: [widgets/alloc]\n---\n\n## Memory\n\nthe only card\n")
    r = _run_gate("clients", "concepts",
                  "--changed-file", "clients/alpha/memory/m1.md",
                  cwd=tmp_path, gateway=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["state"] == "success"


def test_main_refuses_a_clients_dir_outside_the_directory_it_runs_from(tmp_path):
    """Nothing relative to the working directory can name a card in there, so no verdict."""
    _tree(tmp_path / "corpus")
    (tmp_path / "elsewhere").mkdir()
    r = _run_gate(str(tmp_path / "corpus" / "clients"), str(tmp_path / "corpus" / "concepts"),
                  "--changed-file", "corpus/clients/alpha/memory/m1.md",
                  cwd=tmp_path / "elsewhere")
    assert r.returncode != 0
    assert "success" not in r.stdout
    assert "outside the working directory" in r.stderr


def test_main_refuses_a_clients_dir_that_is_the_directory_it_runs_from(tmp_path):
    """A green over an unscored memory change is what the empty prefix used to produce.

    With `clients_dir` resolving to the working directory there is no prefix left to match
    on, so every changed path containing `/memory/` looks like a memory card, while
    `memory_lint` finds no card at all under that root - the ids it builds need a client
    directory above `memory/`. Zero cards read as zero conflicts, and the gate printed
    `state: success` over a change nothing had scored. The gateway is configured here so
    that path is reachable at all: without it the gate stops at the gateway refusal first
    and the green stays hidden. Nothing is sent, because a refusal comes first now and
    zero candidates never reach the scorer.
    """
    _tree(tmp_path)
    r = _run_gate(".", "concepts", "--changed-file", "clients/alpha/memory/m1.md",
                  cwd=tmp_path, gateway=True)
    assert "success" not in r.stdout, f"the gate answered with no prefix to match on: {r.stdout!r}"
    assert r.returncode != 0
    assert "is the working directory" in r.stderr


def test_changed_path_prefix_refuses_the_working_directory(tmp_path, monkeypatch):
    """The tree below the root still answers; the root itself does not."""
    _tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert pcg.changed_path_prefix("clients") == "clients/"
    with pytest.raises(SystemExit) as excinfo:
        pcg.changed_path_prefix(".")
    assert "is the working directory" in str(excinfo.value)


def test_pr_touches_memory_takes_the_prefix_of_a_corpus_below_the_root():
    """The default is the corpus-at-the-root layout the corpus repository calls it with."""
    nested = ["corpus/clients/alpha/memory/m1.md"]
    assert pcg.pr_touches_memory(nested) is False
    assert pcg.pr_touches_memory(nested, "corpus/clients/") is True
    assert pcg.pr_touches_memory(["corpus/concepts/w/a.md"], "corpus/clients/") is False


def test_the_derived_prefix_is_not_the_id_prefix(tmp_path, monkeypatch):
    """Two facts, deliberately apart: card ids stay `clients/...` under any layout."""
    _tree(tmp_path / "corpus")
    monkeypatch.chdir(tmp_path)
    assert pcg.changed_path_prefix("corpus/clients") == "corpus/clients/"
    assert memory_lint.CLIENTS_PREFIX == "clients/"
    ids = memory_lint._memories("corpus/clients")
    assert ids and all(i.startswith(memory_lint.CLIENTS_PREFIX) for i in ids)

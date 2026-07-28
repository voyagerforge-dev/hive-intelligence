import importlib.util
from pathlib import Path

_S = Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _S / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pcg = _load("pr_conflict_gate")


class FakeLLM:
    def __init__(self, prob):
        self._p = prob

    def complete(self, system, user):
        return f'{{"probability": {self._p}, "rationale": "x"}}'


def test_pr_touches_memory():
    assert pcg.pr_touches_memory(["knowledge/okf/clients/alpha/memory/x.md"]) is True
    assert pcg.pr_touches_memory(["knowledge/okf/concepts/widgets/a.md"]) is False
    assert pcg.pr_touches_memory(["README.md"]) is False


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

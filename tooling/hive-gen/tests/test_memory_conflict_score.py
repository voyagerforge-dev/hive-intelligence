import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "memory_conflict_score",
    Path(__file__).resolve().parents[1] / "scripts" / "memory_conflict_score.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)
gate = mod.gate
score_pair = mod.score_pair


class FakeLLM:
    def __init__(self, reply):
        self._reply = reply

    def complete(self, system, user):
        return self._reply


def test_score_pair_parses_probability():
    r = score_pair({"title": "A"}, {"title": "B"}, FakeLLM('{"probability": 0.8, "rationale": "x"}'))
    assert r["probability"] == 0.8


def test_score_pair_fail_safe_on_garbage():
    r = score_pair({"title": "A"}, {"title": "B"}, FakeLLM("not json"))
    assert r["probability"] == 1.0 and "fail-safe" in r["rationale"]


def test_gate_blocks_high_reviews_mid_clears_low():
    mems = {"a": {"title": "A"}, "b": {"title": "B"}, "c": {"title": "C"},
            "d": {"title": "D"}, "e": {"title": "E"}, "f": {"title": "F"}}
    cands = [("a", "b"), ("c", "d"), ("e", "f")]
    replies = {("a", "b"): '{"probability": 0.9, "rationale": "conflict"}',
               ("c", "d"): '{"probability": 0.45, "rationale": "maybe"}',
               ("e", "f"): '{"probability": 0.1, "rationale": "distinct"}'}

    class Router:
        def __init__(self, pair):
            self.pair = pair

        def complete(self, system, user):
            return replies[self.pair]

    blocking, review = gate(cands, mems, None, llm_factory=lambda pair: Router(pair))
    assert [tuple(p) for p in blocking] == [("a", "b")]
    assert [tuple(p) for p in review] == [("c", "d")]

from okfserve.eval import judge_answer, load_qa, run_eval, score_regime, score_selection


def test_load_qa(tmp_path):
    p = tmp_path / "qa.jsonl"
    p.write_text('{"id": "q1", "question": "x?", "expected_card_ids": ["a"]}\n')
    rows = load_qa(p)
    assert rows[0]["expected_card_ids"] == ["a"]


def test_score_selection():
    assert score_selection(["a"], ["a"], ["a"]) == {"select_hit": True, "bundle_hit": True}
    assert score_selection(["a"], ["b"], ["b", "a"]) == {"select_hit": False, "bundle_hit": True}
    assert score_selection(["a"], ["b"], ["b"]) == {"select_hit": False, "bundle_hit": False}


def test_score_regime_counts_cross_regime():
    assert score_regime("ops", ["ops", "ops"]) == {"cross_regime": 0, "regime_ok": True}
    assert score_regime("ops", ["ops", "traditional"]) == {"cross_regime": 1, "regime_ok": False}
    assert score_regime(None, ["ops", "traditional"]) == {"cross_regime": 0, "regime_ok": True}


class JudgeLLM:
    def __init__(self, reply): self._reply = reply
    def complete(self, system, user): return self._reply


def test_judge_answer_parses():
    j = JudgeLLM('{"grounded": true, "correct": true, "note": "ok"}')
    out = judge_answer("q", "a", "ref", j)
    assert out["grounded"] is True and out["correct"] is True


def test_judge_answer_unscored_on_garbage():
    out = judge_answer("q", "a", "ref", JudgeLLM("not json"))
    assert out["note"] == "unscored"


class FixedAnswer:
    def complete(self, system, user): return "answer [a.md]"


class FixedSelect:
    def complete(self, system, user): return '{"card_ids": ["a"]}'


def test_run_eval_aggregates():
    qa = [{"id": "q1", "question": "x?", "expected_card_ids": ["a"]}]

    # stub concepts dir via get_card_fn + monkeypatched load_index/resolve is heavy;
    # instead drive run_eval with a tiny real bundle dir.
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    (d / "a.md").write_text(
        "---\ntitle: A\ndescription: d\nrelated: []\nsources:\n- kind: wms-doc\n  ref: a.md\n"
        "status: approved\n---\n\nbody about x\n")
    res = run_eval(d, qa, select_llm=FixedSelect(), answer_llm=FixedAnswer(),
                   judge_llm=JudgeLLM('{"grounded": true, "correct": true, "note": "ok"}'),
                   get_card_fn=lambda cid: (d / f"{cid}.md").read_text(), mode="progressive")
    assert res["aggregate"]["n"] == 1
    assert res["aggregate"]["select_hit"] == 1
    assert res["aggregate"]["correct"] == 1

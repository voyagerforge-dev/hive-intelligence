from hiveserve.eval import (
    judge_answer,
    load_qa,
    run_eval,
    score_regime,
    score_selection,
    score_version,
)


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


def test_score_version_soft_filter():
    assert score_version("2020", [["2020"], None]) == {"version_ok": True, "off_version": 0}
    assert score_version("2020", [["2018"]]) == {"version_ok": False, "off_version": 1}
    assert score_version("2020", [None, ["2018", "2020"]]) == {"version_ok": True, "off_version": 0}
    assert score_version(None, [["2018"]]) == {"version_ok": True, "off_version": 0}


def test_score_product_counts_cross_product():
    from hiveserve.eval import score_product
    assert score_product("gadgets", ["gadgets", "gadgets"]) == {"cross_product": 0, "product_ok": True}
    assert score_product("gadgets", ["gadgets", "widgets"]) == {"cross_product": 1, "product_ok": False}
    assert score_product("gadgets", ["gadgets", None]) == {"cross_product": 0, "product_ok": True}
    assert score_product(None, ["widgets"]) == {"cross_product": 0, "product_ok": True}


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
        "---\ntitle: A\ndescription: d\nrelated: []\nsources:\n- kind: widgets-doc\n  ref: a.md\n"
        "status: approved\n---\n\nbody about x\n")
    res = run_eval(d, qa, select_llm=FixedSelect(), answer_llm=FixedAnswer(),
                   judge_llm=JudgeLLM('{"grounded": true, "correct": true, "note": "ok"}'),
                   get_card_fn=lambda cid: (d / f"{cid}.md").read_text(), mode="progressive")
    assert res["aggregate"]["n"] == 1
    assert res["aggregate"]["select_hit"] == 1
    assert res["aggregate"]["correct"] == 1


def test_score_correction():
    from hiveserve.eval import score_correction
    assert score_correction(None, []) == {"correction_ok": True}
    assert score_correction("widgets/corrections/fix", ["widgets/corrections/fix"]) == {"correction_ok": True}
    assert score_correction("widgets/corrections/fix", []) == {"correction_ok": False}


def test_score_memory_hit_isolation_and_cross_client():
    from hiveserve.eval import score_memory
    # in-scope hit, no leak
    assert score_memory("clients/alpha/memory/m", ["clients/alpha/memory/m", "widgets/a"],
                        "alpha", ["alpha", None]) == {"memory_ok": True, "cross_client": 0}
    # isolation: no expected memory, none surfaced
    assert score_memory(None, ["widgets/a"], None, [None]) == {"memory_ok": True, "cross_client": 0}
    # cross-client leak: acme scope but a alpha memory surfaced
    r = score_memory(None, ["clients/alpha/memory/m"], "acme", ["alpha"])
    assert r["memory_ok"] is False and r["cross_client"] == 1
    # expected memory missing from bundle -> not ok
    assert score_memory("clients/alpha/memory/m", ["widgets/a"], "alpha", [None])["memory_ok"] is False


# --- a model that returns nothing is a broken run, not a score of zero ------------------

class SilentLLM:
    """A model whose calls return None - four failed retries in `hivegen.llm`, an
    exhausted provider token plan, or a key the gateway rejects."""

    def complete(self, system, user): return None


def _one_card(tmp_path):
    (tmp_path / "a.md").write_text(
        "---\ntitle: A\ndescription: d\nrelated: []\nsources: [a.md]\n---\n\nbody about x\n")
    return [{"id": "q1", "question": "x?", "expected_card_ids": ["a"]}]


def test_run_eval_marks_a_silent_judge_as_a_failure(tmp_path):
    qa = _one_card(tmp_path)
    res = run_eval(tmp_path, qa, select_llm=FixedSelect(), answer_llm=FixedAnswer(),
                   judge_llm=SilentLLM(),
                   get_card_fn=lambda cid: (tmp_path / f"{cid}.md").read_text())
    agg = res["aggregate"]
    assert agg["failed"] is True
    assert agg["judge_empty"] == 1 and agg["answer_empty"] == 0
    assert agg["unscored"] == 1 and agg["correct"] == 0 and agg["grounded"] == 0


def test_run_eval_marks_a_silent_answerer_as_a_failure(tmp_path):
    qa = _one_card(tmp_path)
    res = run_eval(tmp_path, qa, select_llm=FixedSelect(), answer_llm=SilentLLM(),
                   judge_llm=JudgeLLM('{"grounded": false, "correct": false, "note": "empty"}'),
                   get_card_fn=lambda cid: (tmp_path / f"{cid}.md").read_text())
    agg = res["aggregate"]
    # the judge answered, so nothing is `unscored` - the failure is upstream of it
    assert agg["unscored"] == 0
    assert agg["answer_empty"] == 1 and agg["failed"] is True


def test_run_eval_does_not_mark_a_judge_that_merely_replied_with_garbage(tmp_path):
    """Unparseable is a verdict this cannot read; silent is no verdict at all.

    Both score `unscored`, and only the second means the run measured nothing. Failing on
    the first would refuse a run whose models were working.
    """
    qa = _one_card(tmp_path)
    res = run_eval(tmp_path, qa, select_llm=FixedSelect(), answer_llm=FixedAnswer(),
                   judge_llm=JudgeLLM("not json"),
                   get_card_fn=lambda cid: (tmp_path / f"{cid}.md").read_text())
    assert res["aggregate"]["unscored"] == 1
    assert res["aggregate"]["failed"] is False


def test_run_eval_healthy_run_is_not_marked_failed(tmp_path):
    qa = _one_card(tmp_path)
    res = run_eval(tmp_path, qa, select_llm=FixedSelect(), answer_llm=FixedAnswer(),
                   judge_llm=JudgeLLM('{"grounded": true, "correct": true, "note": "ok"}'),
                   get_card_fn=lambda cid: (tmp_path / f"{cid}.md").read_text())
    assert res["aggregate"]["failed"] is False
    assert res["aggregate"]["answer_empty"] == 0 and res["aggregate"]["judge_empty"] == 0


def test_empty_model_roles_names_the_role_and_the_count():
    from hiveserve.eval import empty_model_roles
    assert empty_model_roles({"answer_empty": 0, "judge_empty": 0}) == []
    assert empty_model_roles({"answer_empty": 3, "judge_empty": 70}) == [
        ("answer", 3), ("judge", 70)]

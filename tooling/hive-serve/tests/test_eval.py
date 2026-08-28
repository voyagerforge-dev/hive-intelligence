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


def test_run_eval_scores_facets_from_the_index_it_is_handed(tmp_path):
    """`index` is not a hint: when a caller has already built the index, run_eval scores
    the facets from that list rather than re-reading the corpus into a second one."""
    (tmp_path / "a.md").write_text(
        "---\ntitle: A\ndescription: d\nrelated: []\nregime: traditional\n"
        "sources:\n- kind: widgets-doc\n  ref: a.md\nstatus: approved\n---\n\nbody about x\n")
    qa = [{"id": "q1", "question": "x?", "expected_card_ids": ["a"], "expected_regime": "ops"}]
    judge = JudgeLLM('{"grounded": true, "correct": true, "note": "ok"}')

    on_disk = run_eval(tmp_path, qa, select_llm=FixedSelect(), answer_llm=FixedAnswer(),
                       judge_llm=judge, get_card_fn=lambda cid: (tmp_path / f"{cid}.md").read_text())
    handed = run_eval(tmp_path, qa, select_llm=FixedSelect(), answer_llm=FixedAnswer(),
                      judge_llm=judge, get_card_fn=lambda cid: (tmp_path / f"{cid}.md").read_text(),
                      index=[{"id": "a", "regime": "ops", "version": None, "product": None,
                              "client": None}])

    assert on_disk["aggregate"]["regime_ok"] == 0  # the card on disk is traditional
    assert handed["aggregate"]["regime_ok"] == 1   # the index handed in says ops

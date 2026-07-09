"""Score the OKF Q&A agent over a labelled wave/replen eval set."""
from __future__ import annotations

import json
from pathlib import Path

from okfgen.llm import extract_json

from okfserve.agent import answer_question

_JUDGE_SYS = (
    "You are a strict grader. Given a QUESTION, a candidate ANSWER, and the REFERENCE knowledge "
    "the answer should be based on, judge whether the answer is correct and grounded in the "
    "reference. Reply with ONLY "
    '{"grounded": true|false, "correct": true|false, "note": "<short reason>"}.'
)


def load_qa(path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def score_selection(expected_ids, selected_ids, bundle_ids) -> dict:
    exp = set(expected_ids)
    return {"select_hit": bool(exp & set(selected_ids)),
            "bundle_hit": bool(exp & set(bundle_ids))}


def score_regime(expected_regime, selected_regimes) -> dict:
    if not expected_regime:
        return {"cross_regime": 0, "regime_ok": True}
    cross = sum(1 for r in selected_regimes if r and r != expected_regime)
    return {"cross_regime": cross, "regime_ok": cross == 0}


def score_product(expected_product, selected_products) -> dict:
    if not expected_product:
        return {"cross_product": 0, "product_ok": True}
    cross = sum(1 for p in selected_products if p and p != expected_product)
    return {"cross_product": cross, "product_ok": cross == 0}


def score_version(expected_version, selected_versions) -> dict:
    if not expected_version:
        return {"version_ok": True, "off_version": 0}
    off = sum(1 for v in selected_versions if v and expected_version not in v)
    return {"version_ok": off == 0, "off_version": off}


def score_correction(expected_correction, bundle_correction_ids) -> dict:
    if not expected_correction:
        return {"correction_ok": True}
    return {"correction_ok": expected_correction in set(bundle_correction_ids)}


def judge_answer(question, answer, reference_text, llm) -> dict:
    user = f"QUESTION: {question}\n\nANSWER: {answer}\n\nREFERENCE:\n{reference_text}"
    data = extract_json(llm.complete(_JUDGE_SYS, user) or "")
    if not data or "correct" not in data:
        return {"grounded": None, "correct": None, "note": "unscored"}
    return {"grounded": data.get("grounded"), "correct": data.get("correct"),
            "note": data.get("note", "")}


def run_eval(concepts_dir, qa, *, select_llm, answer_llm, judge_llm, get_card_fn,
             mode: str = "progressive", depth: int = 1, max_cards: int = 8,
             max_chars: int | None = None) -> dict:
    from okfserve.resolver import load_index
    idx = load_index(concepts_dir)
    regime_of = {c["id"]: c.get("regime") for c in idx}
    version_of = {c["id"]: c.get("version") for c in idx}
    product_of = {c["id"]: c.get("product") for c in idx}
    rows = []
    for item in qa:
        res = answer_question(concepts_dir, item["question"], select_llm=select_llm,
                              answer_llm=answer_llm, mode=mode, depth=depth,
                              max_cards=max_cards, max_chars=max_chars)
        sel = score_selection(item["expected_card_ids"], res["selected_ids"], res["bundle_ids"])
        reg = score_regime(item.get("expected_regime"),
                            [regime_of.get(i) for i in res["selected_ids"]])
        ver = score_version(item.get("expected_version"),
                            [version_of.get(i) for i in res["selected_ids"]])
        prod = score_product(item.get("expected_product"),
                             [product_of.get(i) for i in res["selected_ids"]])
        corr = score_correction(item.get("expects_correction"),
                                [b for b in res["bundle_ids"] if "/corrections/" in b])
        ref = "\n\n".join(filter(None, (get_card_fn(cid) for cid in item["expected_card_ids"])))
        verdict = judge_answer(item["question"], res["answer"], ref, judge_llm)
        rows.append({"id": item["id"], "question": item["question"],
                     "selected_ids": res["selected_ids"], "bundle_ids": res["bundle_ids"],
                     **sel, **reg, **ver, **prod, **corr, **verdict, "answer": res["answer"]})
    agg = {
        "n": len(rows),
        "select_hit": sum(1 for r in rows if r["select_hit"]),
        "bundle_hit": sum(1 for r in rows if r["bundle_hit"]),
        "regime_ok": sum(1 for r in rows if r["regime_ok"]),
        "version_ok": sum(1 for r in rows if r["version_ok"]),
        "product_ok": sum(1 for r in rows if r["product_ok"]),
        "correction_ok": sum(1 for r in rows if r["correction_ok"]),
        "correct": sum(1 for r in rows if r["correct"] is True),
        "grounded": sum(1 for r in rows if r["grounded"] is True),
        "unscored": sum(1 for r in rows if r["note"] == "unscored"),
    }
    return {"rows": rows, "aggregate": agg}

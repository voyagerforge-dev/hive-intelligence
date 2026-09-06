"""Score the OKF Q&A agent over a labelled wave/replen eval set."""
from __future__ import annotations

import json
from pathlib import Path

from hivegen.llm import extract_json

from hiveserve.agent import answer_question

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


def score_memory(expected_memory, bundle_ids, expected_client, selected_clients) -> dict:
    cross = sum(1 for c in selected_clients if c and c != expected_client)
    if not expected_memory:
        return {"memory_ok": cross == 0, "cross_client": cross}
    return {"memory_ok": cross == 0 and expected_memory in set(bundle_ids), "cross_client": cross}


def judge_reference(expected_ids, bundle_cards: dict[str, str], get_card_fn) -> str:
    """Build the reference under docs/reference/hive-serve.md's dated scoring contract.

    Reuse saved bundle texts: reloading after a model call could grade evidence different
    from what the answerer saw if a corpus file changed or disappeared during the call.
    """
    ids = dict.fromkeys([*expected_ids, *bundle_cards])
    return "\n\n".join(filter(None, (
        bundle_cards[cid] if cid in bundle_cards else get_card_fn(cid) for cid in ids)))


def judge_answer(question, answer, reference_text, llm) -> dict:
    """One verdict, plus whether the judge model answered at all.

    `unscored` covers two very different events: a judge that replied with something this
    cannot parse, and a judge that replied with nothing. Only the second means the run is
    broken rather than the answer wrong, and telling them apart is what lets `run_eval`
    refuse instead of reporting zeros. See `empty_model_roles`.
    """
    user = f"QUESTION: {question}\n\nANSWER: {answer}\n\nREFERENCE:\n{reference_text}"
    raw = llm.complete(_JUDGE_SYS, user)
    if not (raw or "").strip():
        return {"grounded": None, "correct": None, "note": "unscored", "judge_empty": True}
    data = extract_json(raw)
    if not data or "correct" not in data:
        return {"grounded": None, "correct": None, "note": "unscored", "judge_empty": False}
    return {"grounded": data.get("grounded"), "correct": data.get("correct"),
            "note": data.get("note", ""), "judge_empty": False}


# Every role whose silence invalidates the run. `select` was excluded until 2026-09-06,
# on the reasoning that a selector returning nothing is a retrieval miss the select_hit
# column already measures. That was wrong: a candidate selection default produced no usable
# card_ids on 16 of 16 real selection prompts, 7 of them empty responses, and those 7 were
# reported as a retrieval collapse the harness had never observed. A model that says
# nothing measures nothing, whichever role it holds. The other 9 replies used a different
# JSON schema; an unparseable selection names no cards and stays a genuine miss.
_EMPTY_MODEL_ROLES = ("select", "answer", "judge")


def empty_model_roles(aggregate: dict) -> list[tuple[str, int]]:
    """(role, row count) for every model role that returned nothing on at least one row.

    Even one affected row makes the report incomplete. The counts do not diagnose the
    cause: rejected credentials, unavailable models and exhausted quota can all yield
    empty responses.
    """
    return [(role, aggregate[f"{role}_empty"])
            for role in _EMPTY_MODEL_ROLES if aggregate.get(f"{role}_empty")]


def run_eval(concepts_dir, qa, *, select_llm, answer_llm, judge_llm, get_card_fn,
             mode: str = "progressive", depth: int = 1, max_cards: int = 8,
             max_chars: int | None = None, clients_dir=None) -> dict:
    from hiveserve.resolver import load_index
    idx = load_index(concepts_dir, clients_dir)
    regime_of = {c["id"]: c.get("regime") for c in idx}
    version_of = {c["id"]: c.get("version") for c in idx}
    product_of = {c["id"]: c.get("product") for c in idx}
    client_of = {c["id"]: c.get("client") for c in idx}
    rows = []
    for item in qa:
        res = answer_question(concepts_dir, item["question"], select_llm=select_llm,
                              answer_llm=answer_llm, mode=mode, depth=depth,
                              max_cards=max_cards, max_chars=max_chars,
                              clients_dir=clients_dir, client=item.get("client"))
        sel = score_selection(item["expected_card_ids"], res["selected_ids"], res["bundle_ids"])
        reg = score_regime(item.get("expected_regime"),
                            [regime_of.get(i) for i in res["selected_ids"]])
        ver = score_version(item.get("expected_version"),
                            [version_of.get(i) for i in res["selected_ids"]])
        prod = score_product(item.get("expected_product"),
                             [product_of.get(i) for i in res["selected_ids"]])
        corr = score_correction(item.get("expects_correction"),
                                [b for b in res["bundle_ids"] if "/corrections/" in b])
        mem = score_memory(item.get("expects_memory"), res["bundle_ids"], item.get("client"),
                           [client_of.get(i) for i in res["bundle_ids"]])
        ref = judge_reference(item["expected_card_ids"], res["bundle_cards"], get_card_fn)
        verdict = judge_answer(item["question"], res["answer"], ref, judge_llm)
        rows.append({"id": item["id"], "question": item["question"],
                     "selected_ids": res["selected_ids"], "bundle_ids": res["bundle_ids"],
                     "select_empty": res["select_empty"],
                     "answer_empty": not (res["answer"] or "").strip(),
                     **sel, **reg, **ver, **prod, **corr, **mem, **verdict, "answer": res["answer"]})
    agg = {
        "n": len(rows),
        "select_hit": sum(1 for r in rows if r["select_hit"]),
        "bundle_hit": sum(1 for r in rows if r["bundle_hit"]),
        "regime_ok": sum(1 for r in rows if r["regime_ok"]),
        "version_ok": sum(1 for r in rows if r["version_ok"]),
        "product_ok": sum(1 for r in rows if r["product_ok"]),
        "correction_ok": sum(1 for r in rows if r["correction_ok"]),
        "memory_ok": sum(1 for r in rows if r["memory_ok"]),
        "correct": sum(1 for r in rows if r["correct"] is True),
        "grounded": sum(1 for r in rows if r["grounded"] is True),
        "unscored": sum(1 for r in rows if r["note"] == "unscored"),
        # Not scores: the count of rows on which a model returned nothing at all. Zeros
        # produced this way are the absence of a measurement, and `failed` says so in the
        # written report rather than only on a terminal nobody kept.
        "select_empty": sum(1 for r in rows if r["select_empty"]),
        "answer_empty": sum(1 for r in rows if r["answer_empty"]),
        "judge_empty": sum(1 for r in rows if r["judge_empty"]),
    }
    agg["failed"] = bool(empty_model_roles(agg))
    return {"rows": rows, "aggregate": agg}

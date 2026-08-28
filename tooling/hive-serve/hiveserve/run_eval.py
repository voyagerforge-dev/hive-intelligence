"""Live test entrypoint: run the OKF Q&A agent over a labelled eval set.

Both of the things this needs are corpus-side and neither is derivable from here. The
cards live in the corpus repository, separate from the engine since 2026-08-11, and the
eval sets ship beside them because they name real card ids. So both come from settings:
``CONCEPTS_DIR`` for the cards, ``EVAL_DIR`` for the sets.

This file used to walk up from ``__file__`` for both, which after the split resolved to
the engine repository. It never raised. ``load_index`` over a directory that is not there
returns ``[]``, so an eval against an absent corpus scores every question zero and prints
an aggregate as though it had measured something.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from hivegen.corpus import require_dir
from hivegen.llm import BifrostChat

from hiveserve.config import get_settings
from hiveserve.eval import load_qa, run_eval
from hiveserve.resolver import get_card

USAGE = (
    "usage: run_eval <progressive|ceiling> <qa-set>\n"
    "  qa-set is a bare name resolved under EVAL_DIR, or a path to a .jsonl.\n"
    "  QA sets name real cards, so they live with the corpus, not here: point\n"
    "  EVAL_DIR at your corpus's eval sets."
)


def qa_set_path(qa_arg: str, eval_dir: str) -> Path:
    """Resolve the qa-set argument to a file, or exit saying what was looked for and where.

    A bare name is the documented way to call this and resolves under ``EVAL_DIR``. Anything
    carrying a suffix is taken as a path, so an ad-hoc set outside the corpus still works.
    """
    given = Path(qa_arg)
    if given.suffix:
        if not given.is_file():
            raise SystemExit(f"no eval set at {given} (resolved to {given.resolve()}).")
        return given
    base = require_dir(eval_dir, setting="EVAL_DIR", what="the corpus's eval sets")
    path = base / f"{qa_arg}.jsonl"
    if not path.is_file():
        available = sorted(p.stem for p in base.glob("*.jsonl"))
        raise SystemExit(
            f"no eval set named {qa_arg!r} in EVAL_DIR={base}.\n"
            f"Available: {', '.join(available) if available else '(none)'}")
    return path


def corpus_cards(concepts_dir: str) -> Path:
    """The concept cards to evaluate, refusing an empty corpus as loudly as a missing one.

    An empty result is the failure mode this guards: zero cards scores zero on every
    question, which is indistinguishable from a corpus that is simply bad.
    """
    path = require_dir(concepts_dir, setting="CONCEPTS_DIR", what="the corpus concept cards")
    if not any(path.rglob("*.md")):
        raise SystemExit(
            f"CONCEPTS_DIR={path} holds no cards, so there is nothing to evaluate. "
            "An eval over an empty corpus scores zero on every question and reports it "
            "as a result.")
    return path


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "progressive"
    if mode not in ("progressive", "ceiling"):
        raise SystemExit(f"unknown mode {mode!r}; use 'progressive' or 'ceiling'")
    if len(sys.argv) < 3:
        raise SystemExit(USAGE)
    s = get_settings()
    concepts = corpus_cards(s.concepts_dir)
    qa_path = qa_set_path(sys.argv[2], s.eval_dir)
    qa = load_qa(qa_path)
    select_llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.select_model,
                             timeout_s=s.bifrost_timeout_s)
    answer_llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.answer_model,
                             timeout_s=s.bifrost_timeout_s)
    judge_llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.judge_model,
                            timeout_s=s.bifrost_timeout_s)
    res = run_eval(concepts, qa, select_llm=select_llm, answer_llm=answer_llm,
                   judge_llm=judge_llm, get_card_fn=lambda cid: get_card(concepts, cid),
                   mode=mode, depth=s.resolve_depth, max_cards=s.max_cards,
                   max_chars=s.max_chars)
    # The report is this service's own scratch, so it goes where the other non-ledger
    # scratch goes. It used to be written inside the installed package, which is neither
    # writable nor findable once hive-serve is installed rather than checked out.
    out_dir = Path(s.okf_data_dir) / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / f"report-{mode}-{qa_path.stem}.json"
    report.write_text(json.dumps(res, indent=2))
    print(f"mode={mode} qa={qa_path.stem} aggregate={res['aggregate']} report={report}")


if __name__ == "__main__":
    main()

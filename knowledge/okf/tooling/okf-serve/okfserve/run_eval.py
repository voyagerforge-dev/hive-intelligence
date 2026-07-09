"""Live test entrypoint: run the OKF Q&A agent over the wave/replen eval set."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from okfgen.llm import BifrostChat

from okfserve.config import get_settings
from okfserve.eval import load_qa, run_eval
from okfserve.resolver import get_card


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "progressive"
    if mode not in ("progressive", "ceiling"):
        raise SystemExit(f"unknown mode {mode!r}; use 'progressive' or 'ceiling'")
    # optional 2nd arg: qa set — a bare name under data/ (e.g. corrections_qa) or a path.
    qa_arg = sys.argv[2] if len(sys.argv) > 2 else "wave_replen_qa"
    s = get_settings()
    pkg = Path(__file__).resolve().parents[1]
    concepts = pkg.parents[1] / "concepts"
    qa_path = Path(qa_arg)
    if not qa_path.suffix:
        qa_path = pkg / "data" / f"{qa_arg}.jsonl"
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
    out_dir = pkg / ".eval"
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"report-{mode}-{qa_path.stem}.json").write_text(json.dumps(res, indent=2))
    print(f"mode={mode} qa={qa_path.stem} aggregate={res['aggregate']}")


if __name__ == "__main__":
    main()

"""Live test entrypoint: run the OKF Q&A agent over a labelled eval set.

Both of the things this needs are corpus-side and neither is derivable from here. The
cards live in the corpus repository, separate from the engine since 2026-08-11, and the
eval sets ship beside them because they name real card ids. So both come from settings:
``CONCEPTS_DIR`` for the cards, ``EVAL_DIR`` for the sets, and ``CLIENTS_DIR`` for client
memory when a set exercises it.

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
from hiveserve.resolver import client_of_id, clients_base, get_card, load_index

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
    question, which is indistinguishable from a corpus that is simply bad. "Empty" is
    therefore the loader's own definition, not "holds no .md": ``load_index`` skips
    index.md, log.md and the ``<product>/db/`` tier, so a corpus holding only those
    passes a file count and still indexes nothing.
    """
    path = require_dir(concepts_dir, setting="CONCEPTS_DIR", what="the corpus concept cards")
    if not load_index(path):
        raise SystemExit(
            f"CONCEPTS_DIR={path} holds no cards the index can load, so there is nothing "
            "to evaluate. An eval over an empty corpus scores zero on every question and "
            "reports it as a result. index.md, log.md and the <product>/db/ tier are not "
            "cards, so a corpus holding only those counts as empty here.")
    return path


def required_clients(row: dict) -> set[str]:
    """The clients a qa row needs *cards* for, which is not the identity it asks as.

    A row's ``client`` field is who the question is asked as. An isolation control asks as
    a client that deliberately has *no* memory - having none is exactly how you show that
    another client's memory does not leak into it - and scores correctly with no client
    cards of its own, because ``resolve`` excludes every out-of-scope ``clients/`` card and
    ``score_memory`` then measures the absence. Treating that row as a requirement refuses
    the isolation eval, which is the deploy gate.

    What genuinely needs cards is a row that expects one: ``expects_memory`` names a card
    id, and ``expected_card_ids`` may name ``clients/<client>/...``. The client segment is
    read with the resolver's own derivation, so this and ``load_index`` cannot disagree.
    """
    ids = (row.get("expects_memory"), *(row.get("expected_card_ids") or ()))
    return {name for cid in ids if cid for name in (client_of_id(str(cid)),) if name}


def needs_client_memory(row: dict) -> bool:
    """Whether a row is scored against client memory at all - one definition, both guards."""
    return bool(row.get("expects_memory")) or bool(required_clients(row))


def corpus_clients(clients_dir: str, qa: list[dict], *, concepts: Path,
                   configured: bool) -> Path | None:
    """Client memory for the eval, matching the shape the served path builds.

    ``CLIENTS_DIR`` is genuinely optional: omitting it disables client memory, which is a
    supported deployment. What is not supported is scoring a set that exercises client
    memory without it. ``load_index`` simply never returns the client-scoped cards, every
    such row misses, and the aggregate is reported as a measurement of the served system.

    A directory that merely exists is not a guard, for the same reason a file count is not
    one in :func:`corpus_cards`: the check asks ``load_index`` which clients it can
    actually serve, and :func:`required_clients` reads which clients the rows need cards
    for, so no heuristic is required.

    ``configured`` says whether any source actually supplied ``CLIENTS_DIR``, which is
    provenance rather than a guess from the value: it decides only whether a dead path is
    worth reporting, never whether the set is allowed to run.
    """
    given = str(clients_dir).strip()
    path = clients_base(clients_dir)
    if path is not None and path.is_dir():
        required = sorted({name for row in qa for name in required_clients(row)})
        served = {c["client"] for c in load_index(concepts, path) if c["client"]}
        absent = [c for c in required if c not in served]
        if absent:
            raise SystemExit(
                f"CLIENTS_DIR={given} is a directory, but the index loads no client memory "
                f"for {', '.join(absent)}, whose cards this eval set expects. Client cards "
                "live at <client>/memory/<slug>.md and <client>/issues/<slug>.md, so a "
                "directory that merely exists serves none of them: every row expecting "
                "those cards misses and the aggregate reads as a property of the corpus.")
        return path
    needs = [str(row.get("id", "?")) for row in qa if needs_client_memory(row)]
    if needs:
        raise SystemExit(
            f"CLIENTS_DIR={given or '(unset)'} is not a directory, but this eval set has "
            f"{len(needs)} row(s) that exercise client memory ({', '.join(needs[:5])}"
            f"{', ...' if len(needs) > 5 else ''}). Scored without it every one of them "
            "misses and the aggregate reads as a property of the corpus. Point CLIENTS_DIR "
            "at the corpus's client memory, or use a set that does not need it.")
    # Only when some source actually supplied it. The class default is a relative guess
    # that is a directory almost nowhere, so warning on an untouched one would name a dead
    # path the operator never set, on every run of a deployment with no client memory.
    if path is not None and configured:
        print(f"[run_eval] CLIENTS_DIR={given} is not a directory (resolved to "
              f"{path.resolve()}), so client memory is disabled for this run. No row in "
              "this eval set exercises it, so the aggregate is unaffected - but the path "
              "is dead, and the next set that needs it will refuse.", flush=True)
    return None


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
    clients = corpus_clients(s.clients_dir, qa, concepts=concepts,
                             configured="clients_dir" in s.model_fields_set)
    select_llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.select_model,
                             timeout_s=s.bifrost_timeout_s)
    answer_llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.answer_model,
                             timeout_s=s.bifrost_timeout_s)
    judge_llm = BifrostChat(s.bifrost_base, s.bifrost_api_key, s.judge_model,
                            timeout_s=s.bifrost_timeout_s)
    res = run_eval(concepts, qa, select_llm=select_llm, answer_llm=answer_llm,
                   judge_llm=judge_llm,
                   get_card_fn=lambda cid: get_card(concepts, cid, clients),
                   mode=mode, depth=s.resolve_depth, max_cards=s.max_cards,
                   max_chars=s.max_chars, clients_dir=clients)
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

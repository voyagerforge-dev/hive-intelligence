"""`run_eval` finds the corpus and the eval sets, or says why it cannot.

Both live in the corpus repository, separate from this one since the 2026-08-11 split.
Nothing about where they sit follows from where hive-serve is installed, so both come
from settings; walking up from ``__file__`` lands in the engine repository, where
``concepts/`` is not and ``data/`` no longer is.

The failure this guards against is not a crash. ``load_index`` over a missing directory
returns ``[]``, so an eval against a corpus that is not there scores every question zero
and reports an aggregate as if it had measured something.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import hiveserve.run_eval as run_eval_module
from hiveserve.config import get_settings

CARD = ("---\ntitle: Wave Replen\ndescription: replen feeds waves\nrelated: []\n"
        "sources: [widgets.md]\n---\nBody.\n")
QA_ROW = {"id": "q1", "question": "what feeds waves?", "expected_card_ids": ["wave-replen"]}


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """A corpus repository holding one card and one eval set, with the model stubbed.

    Yields a recorder carrying the paths and whatever ``run_eval`` was handed.
    """
    concepts = tmp_path / "corpus" / "concepts"
    concepts.mkdir(parents=True)
    (concepts / "wave-replen.md").write_text(CARD)
    evals = tmp_path / "corpus" / "eval"
    evals.mkdir()
    (evals / "wave-replen.jsonl").write_text(json.dumps(QA_ROW) + "\n")

    monkeypatch.chdir(tmp_path)  # no .env of the developer's own, and reports land here
    for key in ("CONCEPTS_DIR", "CLIENTS_DIR", "EVAL_DIR"):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()

    rec: dict = {"concepts": concepts, "evals": evals, "ran": False}

    def _run_eval(concepts_dir, qa, **_kw):
        rec["ran"] = True
        rec["concepts_dir"] = Path(concepts_dir)
        rec["qa"] = qa
        return {"aggregate": {"n": len(qa)}, "rows": []}

    monkeypatch.setattr(run_eval_module, "run_eval", _run_eval)
    monkeypatch.setattr(run_eval_module, "BifrostChat", lambda *a, **k: object())
    yield rec
    get_settings.cache_clear()


def _argv(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["run_eval", *args])


def test_eval_scores_the_corpus_named_by_concepts_dir(corpus, monkeypatch):
    """CONCEPTS_DIR is the setting that already exists for this. Use it."""
    monkeypatch.setenv("CONCEPTS_DIR", str(corpus["concepts"]))
    monkeypatch.setenv("EVAL_DIR", str(corpus["evals"]))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "wave-replen")

    run_eval_module.main()

    assert corpus["concepts_dir"] == corpus["concepts"]
    assert list(corpus["concepts_dir"].glob("*.md")), "scored a corpus with no cards in it"


def test_a_bare_qa_set_name_resolves_under_eval_dir(corpus, monkeypatch):
    """The documented calling convention: a bare name, resolved against the corpus's
    eval sets. It used to resolve under a package directory the split removed."""
    monkeypatch.setenv("CONCEPTS_DIR", str(corpus["concepts"]))
    monkeypatch.setenv("EVAL_DIR", str(corpus["evals"]))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "wave-replen")

    run_eval_module.main()

    assert corpus["ran"] is True
    assert corpus["qa"] == [QA_ROW], "did not load the eval set the corpus ships"


def test_an_explicit_path_to_a_qa_set_still_works(corpus, monkeypatch):
    monkeypatch.setenv("CONCEPTS_DIR", str(corpus["concepts"]))
    get_settings.cache_clear()
    _argv(monkeypatch, "ceiling", str(corpus["evals"] / "wave-replen.jsonl"))

    run_eval_module.main()

    assert corpus["qa"] == [QA_ROW]


def test_eval_refuses_when_the_concepts_dir_is_not_there(corpus, monkeypatch, tmp_path):
    """The silent case: an absent corpus scores zero and looks like a bad corpus."""
    monkeypatch.setenv("CONCEPTS_DIR", str(tmp_path / "gone"))
    monkeypatch.setenv("EVAL_DIR", str(corpus["evals"]))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "wave-replen")

    with pytest.raises(SystemExit) as exc:
        run_eval_module.main()
    assert "CONCEPTS_DIR" in str(exc.value)
    assert corpus["ran"] is False


def test_eval_refuses_when_the_concepts_dir_holds_no_cards(corpus, monkeypatch, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("CONCEPTS_DIR", str(empty))
    monkeypatch.setenv("EVAL_DIR", str(corpus["evals"]))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "wave-replen")

    with pytest.raises(SystemExit) as exc:
        run_eval_module.main()
    assert "CONCEPTS_DIR" in str(exc.value)
    assert corpus["ran"] is False


def test_eval_refuses_a_bare_name_when_eval_dir_is_unset(corpus, monkeypatch):
    monkeypatch.setenv("CONCEPTS_DIR", str(corpus["concepts"]))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "wave-replen")

    with pytest.raises(SystemExit) as exc:
        run_eval_module.main()
    assert "EVAL_DIR" in str(exc.value)
    assert corpus["ran"] is False


def test_eval_names_the_sets_it_can_see_when_the_one_asked_for_is_absent(corpus, monkeypatch):
    monkeypatch.setenv("CONCEPTS_DIR", str(corpus["concepts"]))
    monkeypatch.setenv("EVAL_DIR", str(corpus["evals"]))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "no-such-set")

    with pytest.raises(SystemExit) as exc:
        run_eval_module.main()
    assert "no-such-set" in str(exc.value)
    assert "wave-replen" in str(exc.value), "should name the sets it can actually see"
    assert corpus["ran"] is False

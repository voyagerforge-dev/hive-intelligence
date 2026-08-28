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
from hiveserve.resolver import load_index

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

    def _run_eval(concepts_dir, qa, **kw):
        rec["ran"] = True
        rec["concepts_dir"] = Path(concepts_dir)
        rec["qa"] = qa
        rec["kwargs"] = kw
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


# --------------------------------------------------------------------------
# Client memory. CLIENTS_DIR is optional - omitting it disables client memory,
# which is a supported deployment - but an eval set that exercises it and is
# scored without it does not fail, it reports a wrong aggregate: `load_index`
# never returns the client-scoped cards, so every such row misses.
# --------------------------------------------------------------------------

CLIENT_CARD = ("---\ntitle: Acme Wave Note\ndescription: acme's own wave rule\nrelated: []\n"
               "---\nAcme body.\n")
CLIENT_QA_ROW = {"id": "q2", "question": "what does acme do for waves?",
                 "expected_card_ids": ["clients/acme/memory/wave-note"], "client": "acme"}


@pytest.fixture
def client_memory(corpus, tmp_path):
    """Client memory beside the corpus, plus an eval set that needs it."""
    clients = tmp_path / "corpus" / "clients"
    (clients / "acme" / "memory").mkdir(parents=True)
    (clients / "acme" / "memory" / "wave-note.md").write_text(CLIENT_CARD)
    (corpus["evals"] / "acme-memory.jsonl").write_text(json.dumps(CLIENT_QA_ROW) + "\n")
    corpus["clients"] = clients
    return corpus


def test_eval_scores_client_memory_with_the_configured_clients_dir(client_memory, monkeypatch):
    """The eval must measure the same shape the served path builds, which always passes
    clients_dir. Dropping it scores every client-scoped row a miss and prints the total."""
    monkeypatch.setenv("CONCEPTS_DIR", str(client_memory["concepts"]))
    monkeypatch.setenv("CLIENTS_DIR", str(client_memory["clients"]))
    monkeypatch.setenv("EVAL_DIR", str(client_memory["evals"]))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "acme-memory")

    run_eval_module.main()

    assert client_memory["kwargs"]["clients_dir"] == client_memory["clients"]
    get_card_fn = client_memory["kwargs"]["get_card_fn"]
    assert get_card_fn("clients/acme/memory/wave-note") == CLIENT_CARD, \
        "the reference text for a client-scoped card was not resolvable"
    assert "clients/acme/memory/wave-note" in {
        c["id"] for c in load_index(client_memory["concepts"], client_memory["clients"])}, \
        "the eval ran against an index that never loaded the client card it scores"


def test_eval_refuses_a_client_scoped_set_when_clients_dir_is_not_configured(client_memory,
                                                                            monkeypatch):
    """The silent-wrong-aggregate case: the set needs client memory and there is none, so
    it must say so rather than score every one of those rows a miss."""
    monkeypatch.setenv("CONCEPTS_DIR", str(client_memory["concepts"]))
    monkeypatch.setenv("EVAL_DIR", str(client_memory["evals"]))
    monkeypatch.setenv("CLIENTS_DIR", "")
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "acme-memory")

    with pytest.raises(SystemExit) as exc:
        run_eval_module.main()
    assert "CLIENTS_DIR" in str(exc.value)
    assert "q2" in str(exc.value), "should name the rows that need client memory"
    assert client_memory["ran"] is False


def test_eval_runs_without_client_memory_when_the_set_does_not_need_it(corpus, monkeypatch):
    """Omitting CLIENTS_DIR disables client memory and is a supported deployment, so a set
    with no client-scoped rows must still run."""
    monkeypatch.setenv("CONCEPTS_DIR", str(corpus["concepts"]))
    monkeypatch.setenv("EVAL_DIR", str(corpus["evals"]))
    monkeypatch.setenv("CLIENTS_DIR", "")
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "wave-replen")

    run_eval_module.main()

    assert corpus["ran"] is True
    assert corpus["kwargs"]["clients_dir"] is None


def test_eval_refuses_a_corpus_that_holds_only_things_the_index_does_not_count(corpus,
                                                                              monkeypatch,
                                                                              tmp_path):
    """`load_index` skips index.md, log.md and the <product>/db/ tier, so a corpus holding
    only those has .md files and still indexes nothing. Counting files rather than cards
    let it through, and every question then scored zero against an empty index."""
    shell = tmp_path / "shell"
    (shell / "wms" / "db").mkdir(parents=True)
    (shell / "index.md").write_text("---\ntitle: Index\n---\n\nlisting\n")
    (shell / "log.md").write_text("---\ntitle: Log\n---\n\nchangelog\n")
    (shell / "wms" / "db" / "table-x.md").write_text("---\ntitle: TABLE_X\n---\n\ncols\n")
    monkeypatch.setenv("CONCEPTS_DIR", str(shell))
    monkeypatch.setenv("EVAL_DIR", str(corpus["evals"]))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "wave-replen")

    with pytest.raises(SystemExit) as exc:
        run_eval_module.main()
    assert "CONCEPTS_DIR" in str(exc.value)
    assert corpus["ran"] is False


def test_eval_says_out_loud_that_a_dead_clients_dir_disabled_client_memory(corpus, monkeypatch,
                                                                          tmp_path, capsys):
    """A typo'd CLIENTS_DIR does not make this aggregate wrong - no row here selects a
    client-scoped card - so it must not refuse. It must also not degrade in silence, which
    is how the operator finds out only on the next set that does need it."""
    dead = tmp_path / "clients-typo"
    monkeypatch.setenv("CONCEPTS_DIR", str(corpus["concepts"]))
    monkeypatch.setenv("EVAL_DIR", str(corpus["evals"]))
    monkeypatch.setenv("CLIENTS_DIR", str(dead))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "wave-replen")

    run_eval_module.main()

    out = capsys.readouterr().out
    assert "CLIENTS_DIR" in out and str(dead) in out
    assert corpus["ran"] is True
    assert corpus["kwargs"]["clients_dir"] is None


def test_eval_refuses_a_clients_dir_that_serves_none_of_the_clients_the_set_names(
        client_memory, monkeypatch, tmp_path):
    """CLIENTS_DIR=/corpus/client, a singular typo landing on a real but empty scratch dir.
    is_dir() passes, load_index finds no client cards, every acme row misses, and the
    aggregate is printed as a measurement. Existing is not a guard."""
    typo = tmp_path / "client"
    typo.mkdir()
    monkeypatch.setenv("CONCEPTS_DIR", str(client_memory["concepts"]))
    monkeypatch.setenv("EVAL_DIR", str(client_memory["evals"]))
    monkeypatch.setenv("CLIENTS_DIR", str(typo))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "acme-memory")

    with pytest.raises(SystemExit) as exc:
        run_eval_module.main()
    assert "CLIENTS_DIR" in str(exc.value)
    assert "acme" in str(exc.value), "should name the client it cannot serve"
    assert client_memory["ran"] is False


def test_eval_refuses_a_client_tree_whose_cards_the_index_does_not_load(client_memory,
                                                                       monkeypatch,
                                                                       tmp_path):
    """The client directory is there and holds markdown, but not at the paths load_index
    reads - only <client>/memory/ and <client>/issues/ are cards. The guard has to count
    what the consumer counts, not what happens to exist."""
    hollow = tmp_path / "hollow"
    (hollow / "acme" / "notes").mkdir(parents=True)
    (hollow / "acme" / "notes" / "scratch.md").write_text(CLIENT_CARD)
    monkeypatch.setenv("CONCEPTS_DIR", str(client_memory["concepts"]))
    monkeypatch.setenv("EVAL_DIR", str(client_memory["evals"]))
    monkeypatch.setenv("CLIENTS_DIR", str(hollow))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "acme-memory")

    with pytest.raises(SystemExit) as exc:
        run_eval_module.main()
    assert "CLIENTS_DIR" in str(exc.value) and "acme" in str(exc.value)
    assert client_memory["ran"] is False

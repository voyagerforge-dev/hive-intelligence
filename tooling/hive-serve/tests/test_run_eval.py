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


# The isolation control: asked AS beta, expecting only a shared card. beta deliberately
# has no memory of its own - that is how the set demonstrates acme's memory does not leak
# into it - so the row needs no client cards and scores without any.
ISOLATION_QA_ROW = {"id": "q3", "question": "what feeds waves?",
                    "expected_card_ids": ["wave-replen"], "client": "beta"}
GHOST_QA_ROW = {"id": "q4", "question": "what does ghost do for waves?",
                "expected_card_ids": ["clients/ghost/memory/note"], "client": "ghost"}


@pytest.fixture
def client_memory(corpus, tmp_path):
    """Client memory beside the corpus, plus eval sets that do and do not need it."""
    clients = tmp_path / "corpus" / "clients"
    (clients / "acme" / "memory").mkdir(parents=True)
    (clients / "acme" / "memory" / "wave-note.md").write_text(CLIENT_CARD)
    (corpus["evals"] / "acme-memory.jsonl").write_text(json.dumps(CLIENT_QA_ROW) + "\n")
    (corpus["evals"] / "isolation.jsonl").write_text(json.dumps(ISOLATION_QA_ROW) + "\n")
    (corpus["evals"] / "ghost-memory.jsonl").write_text(json.dumps(GHOST_QA_ROW) + "\n")
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


def test_an_unconfigured_clients_dir_default_is_not_reported_as_a_dead_path(corpus,
                                                                           monkeypatch,
                                                                           capsys):
    """CLIENTS_DIR's class default is a relative guess that is a directory almost nowhere.
    Warning about it names a path the operator never set, on every run of a deployment
    that simply has no client memory - noise that trains people to ignore the real one."""
    monkeypatch.setenv("CONCEPTS_DIR", str(corpus["concepts"]))
    monkeypatch.setenv("EVAL_DIR", str(corpus["evals"]))
    monkeypatch.delenv("CLIENTS_DIR", raising=False)
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "wave-replen")

    run_eval_module.main()

    assert "CLIENTS_DIR" not in capsys.readouterr().out
    assert corpus["ran"] is True
    assert corpus["kwargs"]["clients_dir"] is None


def test_an_unconfigured_clients_dir_default_still_refuses_a_set_that_needs_client_memory(
        client_memory, monkeypatch):
    """Staying quiet about the default must not extend to the case that actually matters:
    a set with client rows and nowhere to load them from is the wrong-aggregate bug."""
    monkeypatch.setenv("CONCEPTS_DIR", str(client_memory["concepts"]))
    monkeypatch.setenv("EVAL_DIR", str(client_memory["evals"]))
    monkeypatch.delenv("CLIENTS_DIR", raising=False)
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "acme-memory")

    with pytest.raises(SystemExit) as exc:
        run_eval_module.main()
    assert "CLIENTS_DIR" in str(exc.value)
    assert client_memory["ran"] is False


def test_a_clients_dir_explicitly_set_to_the_default_value_is_still_reported_when_dead(
        corpus, monkeypatch, capsys):
    """Whether it was configured is provenance, not a guess from the value. The default is
    the value docs publish, so it is a plausible thing to write down - an operator who did
    write it down and whose corpus then moved must still be told the path is dead."""
    from hiveserve.config import Settings

    default = Settings.model_fields["clients_dir"].default
    monkeypatch.setenv("CONCEPTS_DIR", str(corpus["concepts"]))
    monkeypatch.setenv("EVAL_DIR", str(corpus["evals"]))
    monkeypatch.setenv("CLIENTS_DIR", default)
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "wave-replen")

    run_eval_module.main()

    out = capsys.readouterr().out
    assert "CLIENTS_DIR" in out and default in out
    assert corpus["ran"] is True
    assert corpus["kwargs"]["clients_dir"] is None


def test_an_isolation_control_row_runs_though_its_client_has_no_cards(client_memory,
                                                                     monkeypatch):
    """The deploy gate. A control client has no memory ON PURPOSE - that is what proves
    another client's memory does not reach it - so a row asked as that client, expecting
    only a shared card, must score rather than be refused. `resolve` drops every
    out-of-scope clients/ card and `score_memory` measures the absence; nothing about it
    needs a card under CLIENTS_DIR."""
    monkeypatch.setenv("CONCEPTS_DIR", str(client_memory["concepts"]))
    monkeypatch.setenv("CLIENTS_DIR", str(client_memory["clients"]))
    monkeypatch.setenv("EVAL_DIR", str(client_memory["evals"]))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "isolation")

    run_eval_module.main()

    assert client_memory["ran"] is True, "refused the isolation eval, which is the gate"
    assert client_memory["qa"] == [ISOLATION_QA_ROW]
    assert client_memory["kwargs"]["clients_dir"] == client_memory["clients"], \
        "scored isolation against an index with no client memory to leak"


def test_a_row_expecting_a_missing_clients_cards_still_refuses(client_memory, monkeypatch):
    """The other half of the distinction: this row does not merely ask as ghost, it expects
    ghost's card. There is none, so every such row misses and the aggregate is wrong."""
    monkeypatch.setenv("CONCEPTS_DIR", str(client_memory["concepts"]))
    monkeypatch.setenv("CLIENTS_DIR", str(client_memory["clients"]))
    monkeypatch.setenv("EVAL_DIR", str(client_memory["evals"]))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "ghost-memory")

    with pytest.raises(SystemExit) as exc:
        run_eval_module.main()
    assert "CLIENTS_DIR" in str(exc.value)
    assert "ghost" in str(exc.value)
    assert client_memory["ran"] is False


def test_an_isolation_set_does_not_force_client_memory_to_be_configured(client_memory,
                                                                       monkeypatch):
    """Asking as a client is not a requirement for client cards, so a set of only control
    rows must still run on a deployment that has client memory switched off."""
    monkeypatch.setenv("CONCEPTS_DIR", str(client_memory["concepts"]))
    monkeypatch.setenv("EVAL_DIR", str(client_memory["evals"]))
    monkeypatch.setenv("CLIENTS_DIR", "")
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "isolation")

    run_eval_module.main()

    assert client_memory["ran"] is True
    assert client_memory["kwargs"]["clients_dir"] is None


def test_an_isolation_only_set_runs_but_says_cross_client_was_unexercised(client_memory,
                                                                           monkeypatch,
                                                                           capsys):
    """`score_memory` passes a control row when no out-of-scope client card reached the
    bundle. With no client cards served at all, none can, so every row passes and the
    aggregate reads as a perfect cross-client isolation score for a run that had nothing
    to leak. It must still run - refusing blocks the gate - but it must not be readable as
    a measurement it did not make."""
    monkeypatch.setenv("CONCEPTS_DIR", str(client_memory["concepts"]))
    monkeypatch.setenv("EVAL_DIR", str(client_memory["evals"]))
    monkeypatch.setenv("CLIENTS_DIR", "")
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "isolation")

    run_eval_module.main()

    out = capsys.readouterr().out
    assert client_memory["ran"] is True, "refused the isolation eval, which is the gate"
    assert "UNEXERCISED" in out
    assert "beta" in out, "should name the identity whose isolation was not measured"


def test_the_unexercised_notice_also_fires_when_a_configured_clients_dir_is_dead(client_memory,
                                                                            monkeypatch,
                                                                            tmp_path,
                                                                            capsys):
    """Unset and set-but-dead reach the same empty index, so both must say it. The dead-path
    notice must also stop claiming the aggregate is unaffected, because it is not."""
    monkeypatch.setenv("CONCEPTS_DIR", str(client_memory["concepts"]))
    monkeypatch.setenv("EVAL_DIR", str(client_memory["evals"]))
    monkeypatch.setenv("CLIENTS_DIR", str(tmp_path / "clients-typo"))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "isolation")

    run_eval_module.main()

    out = capsys.readouterr().out
    assert client_memory["ran"] is True
    assert "UNEXERCISED" in out
    assert "aggregate is unaffected" not in out, "claimed a measurement it did not make"


def test_no_unexercised_notice_when_client_cards_are_actually_served(client_memory, monkeypatch,
                                                                capsys):
    """The other half: acme's memory is in the index, so beta's control row measures a real
    absence and the run is a genuine isolation result."""
    monkeypatch.setenv("CONCEPTS_DIR", str(client_memory["concepts"]))
    monkeypatch.setenv("CLIENTS_DIR", str(client_memory["clients"]))
    monkeypatch.setenv("EVAL_DIR", str(client_memory["evals"]))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "isolation")

    run_eval_module.main()

    out = capsys.readouterr().out
    assert client_memory["ran"] is True
    assert "UNEXERCISED" not in out


def test_cross_client_is_unexercised_when_the_only_served_client_is_the_asking_one(
        client_memory, monkeypatch, tmp_path, capsys):
    """A non-empty clients tree is not enough. `score_memory` counts a card only when its
    client DIFFERS from the row's, so a tree holding only beta's own cards serves nothing
    that could count against a set asking as beta: every row passes with nothing to leak."""
    beta_only = tmp_path / "beta-only"
    (beta_only / "beta" / "memory").mkdir(parents=True)
    (beta_only / "beta" / "memory" / "note.md").write_text(CLIENT_CARD)
    monkeypatch.setenv("CONCEPTS_DIR", str(client_memory["concepts"]))
    monkeypatch.setenv("CLIENTS_DIR", str(beta_only))
    monkeypatch.setenv("EVAL_DIR", str(client_memory["evals"]))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "isolation")

    run_eval_module.main()

    assert client_memory["ran"] is True
    assert "UNEXERCISED" in capsys.readouterr().out


def test_the_persisted_report_records_that_cross_client_was_unexercised(client_memory,
                                                                             monkeypatch,
                                                                             tmp_path):
    """The terminal scrollback is gone by the time anyone reads the result. The report is
    what the deploy gate is judged on, so the caveat has to be in it."""
    monkeypatch.setenv("CONCEPTS_DIR", str(client_memory["concepts"]))
    monkeypatch.setenv("EVAL_DIR", str(client_memory["evals"]))
    monkeypatch.setenv("CLIENTS_DIR", "")
    monkeypatch.setenv("OKF_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "isolation")

    run_eval_module.main()

    report = json.loads(
        (tmp_path / "data" / "eval" / "report-progressive-isolation.json").read_text())
    assert report["aggregate"]["cross_client_unexercised"] is True


def test_a_measurable_cross_client_run_is_not_flagged_in_the_report(client_memory, monkeypatch,
                                                                tmp_path):
    """acme's cards are served and the set asks as beta, so a leak would have something to
    show. That run is a real result and must not carry the caveat."""
    monkeypatch.setenv("CONCEPTS_DIR", str(client_memory["concepts"]))
    monkeypatch.setenv("CLIENTS_DIR", str(client_memory["clients"]))
    monkeypatch.setenv("EVAL_DIR", str(client_memory["evals"]))
    monkeypatch.setenv("OKF_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "isolation")

    run_eval_module.main()

    report = json.loads(
        (tmp_path / "data" / "eval" / "report-progressive-isolation.json").read_text())
    assert report["aggregate"]["cross_client_unexercised"] is False


def test_a_single_client_memory_set_is_not_described_as_having_a_vacuous_memory_ok(
        client_memory, monkeypatch, tmp_path, capsys):
    """acme's own memory set, with only acme served. cross_client cannot fail here - there
    is no other client's card to leak - but memory_ok is a real measurement: with cross
    structurally zero it reduces to whether acme's own card was retrieved, which can fail.
    The notice and the report must scope themselves to cross_client and claim nothing else."""
    monkeypatch.setenv("CONCEPTS_DIR", str(client_memory["concepts"]))
    monkeypatch.setenv("CLIENTS_DIR", str(client_memory["clients"]))
    monkeypatch.setenv("EVAL_DIR", str(client_memory["evals"]))
    monkeypatch.setenv("OKF_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "acme-memory")

    run_eval_module.main()

    out = capsys.readouterr().out
    assert client_memory["ran"] is True
    assert "cross_client is UNEXERCISED" in out, \
        "the claim must name cross_client alone, not memory_ok with it"
    report = json.loads(
        (tmp_path / "data" / "eval" / "report-progressive-acme-memory.json").read_text())
    assert report["aggregate"]["cross_client_unexercised"] is True
    assert "memory_ok_unexercised" not in report["aggregate"]


def test_a_two_client_set_flags_neither_column(client_memory, monkeypatch, tmp_path):
    """acme's cards are served and beta's control row asks as beta, so a leak into beta had
    something to show. Nothing about this run is unexercised."""
    (client_memory["evals"] / "both.jsonl").write_text(
        json.dumps(CLIENT_QA_ROW) + "\n" + json.dumps(ISOLATION_QA_ROW) + "\n")
    monkeypatch.setenv("CONCEPTS_DIR", str(client_memory["concepts"]))
    monkeypatch.setenv("CLIENTS_DIR", str(client_memory["clients"]))
    monkeypatch.setenv("EVAL_DIR", str(client_memory["evals"]))
    monkeypatch.setenv("OKF_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    _argv(monkeypatch, "progressive", "both")

    run_eval_module.main()

    report = json.loads(
        (tmp_path / "data" / "eval" / "report-progressive-both.json").read_text())
    assert report["aggregate"]["cross_client_unexercised"] is False

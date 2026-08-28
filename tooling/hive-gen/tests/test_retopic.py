"""`retopic` is told where the atomic documents are, and refuses when it is not.

It used to fall back to ``Path(__file__).parents[3] / "atomic"``, which since the
2026-08-11 split is the engine repository. That directory is not there, ``glob`` over a
directory that is not there yields nothing and raises nothing, and the pass printed a
distribution of zero and exited 0 - a re-topic run that looked like it had found nothing
to do rather than one that had not looked anywhere real.

The corpus profile is the same shape of problem one step along: it is resolved from the
documents, so it is resolved *after* them, and from the validated setting rather than from
``os.environ``, which a ``.env``-supplied ATOMIC_DIR never reaches.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

from hivegen import retopic
from hivegen.config import get_settings

DOC = '---\ntitle: "Wave Guide"\ntopic: "reference"\nversion: "2021"\n---\nBody.\n'
PROFILE = 'retopic_bucket: "reference"\nguide_topics:\n  waves: "wave planning and release"\n'


@pytest.fixture
def atomic(tmp_path, monkeypatch):
    """A corpus with documents and a profile beside them, and an unrelated working dir.

    The working directory deliberately holds no corpus-profile.yaml, so the only candidate
    that can resolve is the one beside ATOMIC_DIR - which is the candidate the docs promise
    and the one that was not being generated.
    """
    corpus = tmp_path / "corpus"
    docs = corpus / "atomic"
    docs.mkdir(parents=True)
    (docs / "wave-guide-2021.md").write_text(DOC)
    (corpus / "corpus-profile.yaml").write_text(PROFILE)

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)  # no .env and no profile of the developer's own
    monkeypatch.setenv("BIFROST_BASE", "http://bf/v1")
    monkeypatch.setenv("BIFROST_API_KEY", "k")
    monkeypatch.delenv("ATOMIC_DIR", raising=False)
    monkeypatch.delenv("CORPUS_PROFILE", raising=False)
    get_settings.cache_clear()
    yield docs
    get_settings.cache_clear()


def test_newest_docs_reads_the_documents_in_the_configured_atomic_dir(atomic, monkeypatch):
    """The point of the pass: it must actually find the documents it is meant to re-topic."""
    monkeypatch.setenv("ATOMIC_DIR", str(atomic))
    get_settings.cache_clear()

    assert [p.name for p in retopic.newest_docs()] == ["wave-guide-2021.md"]


def test_the_profile_beside_a_dot_env_supplied_atomic_dir_resolves(atomic, monkeypatch):
    """The remedy the refusal names has to be one that works. Settings are `.env`-backed and
    pydantic-settings never writes to os.environ, so a profile lookup that reads the
    environment cannot see an ATOMIC_DIR set the way this package's own .env.example says to
    set it - and reports the profile missing while it sits exactly where it was told to."""
    (Path.cwd() / ".env").write_text(f"ATOMIC_DIR={atomic}\n")
    get_settings.cache_clear()

    assert get_settings().atomic_dir == str(atomic), "fixture did not exercise the .env path"
    assert "ATOMIC_DIR" not in os.environ, "the setting must not have reached the environment"
    assert [p.name for p in retopic.newest_docs()] == ["wave-guide-2021.md"]


def test_newest_docs_refuses_when_the_atomic_dir_is_not_configured(atomic):
    """Unset must stop the pass rather than glob a guessed directory: the guess is what
    put this lookup in the engine repository."""
    with pytest.raises(SystemExit) as exc:
        retopic.newest_docs()
    assert "ATOMIC_DIR" in str(exc.value)


def test_an_unset_atomic_dir_names_atomic_dir_and_not_the_corpus_profile(atomic):
    """With nothing configured at all, both guards would fire. The path guard must be the
    one that speaks, or the operator is sent to set CORPUS_PROFILE while the setting that is
    actually unset is never named - the same misattribution `hivegen.run` is ordered against."""
    with pytest.raises(SystemExit) as exc:
        retopic.newest_docs()
    message = str(exc.value)
    assert "ATOMIC_DIR" in message
    assert "CORPUS_PROFILE" not in message, "blamed the profile for an unset document path"


def test_newest_docs_refuses_an_atomic_dir_that_is_not_there(atomic, monkeypatch, tmp_path):
    missing = tmp_path / "gone"
    monkeypatch.setenv("ATOMIC_DIR", str(missing))
    get_settings.cache_clear()

    with pytest.raises(SystemExit) as exc:
        retopic.newest_docs()
    assert "ATOMIC_DIR" in str(exc.value) and str(missing) in str(exc.value)


def test_importing_retopic_does_not_need_the_atomic_dir(tmp_path, monkeypatch):
    """Resolution is deliberately lazy. Refusing at import would mean `import
    hivegen.retopic` raised SystemExit for anyone who has not configured ATOMIC_DIR,
    which is a new failure rather than a fixed one."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ATOMIC_DIR", raising=False)
    get_settings.cache_clear()

    importlib.reload(retopic)  # must not raise

    get_settings.cache_clear()


def test_the_pass_refuses_rather_than_reporting_zero_when_no_profile_is_found(
        atomic, monkeypatch, tmp_path, capsys):
    """The sibling of the dead ATOMIC_DIR, reached with ATOMIC_DIR correct. With no corpus
    profile the bucket is "" and the topics are {}, so every document carrying a topic is
    skipped and the pass prints "total: 0  applied: True" and exits 0 - indistinguishable
    from a corpus with nothing left to re-topic. It must name the vocabulary it needs."""
    bare = tmp_path / "bare" / "atomic"
    bare.mkdir(parents=True)
    (bare / "wave-guide-2021.md").write_text(DOC)
    before = (bare / "wave-guide-2021.md").read_text()
    monkeypatch.setenv("ATOMIC_DIR", str(bare))
    monkeypatch.setattr(retopic, "BifrostChat", lambda *a, **k: object())
    monkeypatch.setattr("sys.argv", ["retopic", "--apply"])
    get_settings.cache_clear()

    with pytest.raises(SystemExit) as exc:
        retopic.main()

    message = str(exc.value)
    assert "CORPUS_PROFILE" in message, "should name how to supply the vocabulary"
    assert "corpus-profile.yaml" in message
    assert "total:" not in capsys.readouterr().out, "reported a zero instead of refusing"
    assert (bare / "wave-guide-2021.md").read_text() == before


def test_the_pass_refuses_when_a_profile_is_present_but_defines_no_guide_topics(
        atomic, monkeypatch, tmp_path):
    """A profile that exists but declares nothing to classify into is not a missing profile,
    so the refusal names the file and the keys rather than sending the operator to set
    CORPUS_PROFILE, which is already right."""
    partial = tmp_path / "partial"
    docs = partial / "atomic"
    docs.mkdir(parents=True)
    profile = partial / "corpus-profile.yaml"
    profile.write_text("products: {WIDGETS: widgets}\n")
    monkeypatch.setenv("ATOMIC_DIR", str(docs))
    get_settings.cache_clear()

    with pytest.raises(SystemExit) as exc:
        retopic.newest_docs()

    message = str(exc.value)
    assert str(profile) in message
    assert "retopic_bucket" in message and "guide_topics" in message

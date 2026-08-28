from hivegen.load import Doc
from hivegen.run import generate_drafts
from hivegen.taxonomy import Concept


class FakeLLM:
    def complete(self, system, user):
        if "classify" in system.lower():
            return '{"concept_id": "wave-template"}'
        return ('{"title": "Wave Template", "description": "d", "tags": ["w"], '
                '"related": [], "body": "Prose."}')


def test_generate_drafts_writes_one_card_per_concept(tmp_path):
    docs = [Doc("example_prefix/docs/wave-template.md", "example_prefix/docs/wave-template.md", "raw")]
    concepts = [Concept(id="wave-template", title="Wave Template")]
    drafts = tmp_path / "drafts"
    pipeline = tmp_path / ".pipeline"
    written = generate_drafts(docs, concepts, FakeLLM(), FakeLLM(),
                              drafts_dir=drafts, max_chars=1000, today="2026-06-29",
                              pipeline_dir=pipeline)
    assert written == ["wave-template.md"]
    assert (drafts / "wave-template.md").read_text().count("status: draft") == 1
    assert (pipeline / "assignments.yaml").exists()  # curation artifact (assignments + excluded)


def test_generate_drafts_skips_existing_draft(tmp_path):
    """A concept whose draft already exists must not be overwritten or returned."""
    docs = [Doc("example_prefix/docs/wave-template.md", "example_prefix/docs/wave-template.md", "raw")]
    concepts = [Concept(id="wave-template", title="Wave Template")]
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    original_content = "pre-existing operator edit"
    (drafts / "wave-template.md").write_text(original_content)
    written = generate_drafts(docs, concepts, FakeLLM(), FakeLLM(),
                              drafts_dir=drafts, max_chars=1000, today="2026-06-29")
    assert written == []  # existing draft not in returned list
    assert (drafts / "wave-template.md").read_text() == original_content  # content unchanged


# --------------------------------------------------------------------------
# Where the corpus is. Since the 2026-08-11 split it is a separate repository,
# so `main` is told through CARD_CORPUS_ROOT rather than walking up from
# __file__: that arithmetic lands in the engine repository, where an approved
# taxonomy never is, and the run silently re-proposes one instead of distilling.
# The name is hive-gen's own: hive-prep's CORPUS_ROOT is the raw documents going
# in, and one exported name would have been read as both.
# --------------------------------------------------------------------------

from pathlib import Path

import pytest

import hivegen.llm
import hivegen.run
import hivegen.taxonomy
from hivegen.config import get_settings
from hivegen.taxonomy import write_taxonomy

DOC = "---\nslug: wave-template\ntopic: waves\n---\nWave template body.\n"


@pytest.fixture
def corpus_run(tmp_path, monkeypatch):
    """A corpus with one approved taxonomy, an atomic dir, and every model call stubbed.

    Returns a recorder dict; `run()` invokes `hivegen.run.main` against it.
    """
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    write_taxonomy(corpus / "taxonomy.yaml",
                   [Concept(id="wave-template", title="Wave Template")])
    atomic = tmp_path / "atomic"
    atomic.mkdir()
    (atomic / "wave-template.md").write_text(DOC)

    monkeypatch.chdir(tmp_path)  # no .env of the developer's own
    monkeypatch.setenv("ATOMIC_DIR", str(atomic))
    monkeypatch.setenv("BIFROST_BASE", "http://bf/v1")
    monkeypatch.setenv("BIFROST_API_KEY", "k")
    monkeypatch.delenv("SLICE_AREA", raising=False)
    monkeypatch.delenv("CARD_CORPUS_ROOT", raising=False)
    monkeypatch.delenv("CORPUS_ROOT", raising=False)  # hive-prep's, a different tree
    get_settings.cache_clear()

    rec: dict = {"corpus": corpus, "proposed": False}

    def _proposed(*_a, **_k):
        rec["proposed"] = True
        return []

    def _drafts(_docs, concepts, *_a, drafts_dir, pipeline_dir=None, **_k):
        rec["concept_ids"] = [c.id for c in concepts]
        rec["drafts_dir"] = Path(drafts_dir)
        rec["pipeline_dir"] = Path(pipeline_dir) if pipeline_dir else None
        return []

    monkeypatch.setattr(hivegen.taxonomy, "propose_taxonomy", _proposed)
    monkeypatch.setattr(hivegen.llm, "BifrostChat", lambda *a, **k: object())
    monkeypatch.setattr(hivegen.run, "generate_drafts", _drafts)
    yield rec
    get_settings.cache_clear()


def test_run_distils_from_the_approved_taxonomy_in_the_configured_corpus(corpus_run, monkeypatch):
    """The whole point of gate 1: an approved taxonomy already in the corpus must be FOUND
    and distilled from, not silently re-proposed from scratch."""
    monkeypatch.setenv("CARD_CORPUS_ROOT", str(corpus_run["corpus"]))
    get_settings.cache_clear()

    hivegen.run.main()

    assert corpus_run["proposed"] is False, "re-proposed a taxonomy the corpus already has"
    assert corpus_run["concept_ids"] == ["wave-template"]
    assert corpus_run["drafts_dir"] == corpus_run["corpus"] / "drafts"
    assert corpus_run["pipeline_dir"].is_relative_to(corpus_run["corpus"])


def test_run_refuses_when_the_corpus_root_is_not_configured(corpus_run):
    """Unset must stop the run, not fall back to a guess: a guess is what put the taxonomy
    lookup in the wrong repository."""
    with pytest.raises(SystemExit) as exc:
        hivegen.run.main()
    assert "CARD_CORPUS_ROOT" in str(exc.value)
    assert corpus_run["proposed"] is False


def test_run_refuses_when_the_corpus_root_does_not_exist(corpus_run, monkeypatch, tmp_path):
    missing = tmp_path / "not-a-corpus"
    monkeypatch.setenv("CARD_CORPUS_ROOT", str(missing))
    get_settings.cache_clear()

    with pytest.raises(SystemExit) as exc:
        hivegen.run.main()
    assert "CARD_CORPUS_ROOT" in str(exc.value) and str(missing) in str(exc.value)
    assert corpus_run["proposed"] is False


def test_run_does_not_take_the_raw_document_tree_from_hive_preps_corpus_root(corpus_run,
                                                                            monkeypatch,
                                                                            tmp_path):
    """The two settings name different trees. An operator who exported CORPUS_ROOT for the
    ingest stage and then ran hive-gen must not have that tree accepted as the card corpus:
    it is a real directory, so the "set, and a directory" guard cannot catch it, and hive-gen
    would find no taxonomy in it and re-propose one straight into the raw documents."""
    ingest = tmp_path / "ingest_content"
    ingest.mkdir()
    monkeypatch.setenv("CORPUS_ROOT", str(ingest))
    get_settings.cache_clear()

    with pytest.raises(SystemExit) as exc:
        hivegen.run.main()
    assert "CARD_CORPUS_ROOT" in str(exc.value)
    assert corpus_run["proposed"] is False
    assert list(ingest.iterdir()) == [], "wrote a draft taxonomy into the raw document tree"

from okfgen.load import Doc
from okfgen.run import generate_drafts
from okfgen.taxonomy import Concept


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

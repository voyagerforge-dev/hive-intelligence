import yaml

from hivegen.card import build_okf_card, distill_concept
from hivegen.load import Doc
from hivegen.taxonomy import Concept


def test_build_okf_card_frontmatter_and_body():
    md = build_okf_card({
        "type": "concept", "title": "Wave Template", "description": "d",
        "tags": ["waving"], "resource": "wmos",
        "sources": [{"kind": "wms-doc", "ref": "example_prefix/docs/wave-template.md"}],
        "related": ["cartonization"], "distilled_at": "2026-06-29", "status": "draft",
    }, "Body prose.")
    assert md.startswith("---\n")
    fm = yaml.safe_load(md.split("---")[1])
    assert fm["title"] == "Wave Template" and fm["status"] == "draft"
    assert fm["related"] == ["cartonization"]
    assert md.rstrip().endswith("Body prose.")


class FakeLLM:
    def complete(self, system, user):
        return ('{"title": "Wave Template", "description": "How waving is configured", '
                '"tags": ["waving"], "related": ["replenishment"], "body": "Curated prose."}')


def test_distill_concept_emits_draft_card():
    concept = Concept(id="wave-template", title="Wave Template")
    docs = [Doc("example_prefix/docs/wave-template.md", "example_prefix/docs/wave-template.md", "raw")]
    md = distill_concept(concept, docs, FakeLLM(), max_chars=1000, today="2026-06-29",
                         related_ids=["replenishment"])
    fm = yaml.safe_load(md.split("---")[1])
    assert fm["status"] == "draft" and fm["type"] == "concept" and fm["resource"] == "wmos"
    assert fm["sources"][0]["ref"] == "example_prefix/docs/wave-template.md"
    assert "Curated prose." in md
    assert fm["related"] == ["replenishment"]


def test_distill_concept_related_bogus_id_filtered():
    """LLM returns an id not in related_ids — it must be stripped out."""
    concept = Concept(id="wave-template", title="Wave Template")
    docs = [Doc("example_prefix/docs/wave-template.md", "example_prefix/docs/wave-template.md", "raw")]
    # FakeLLM returns related:["replenishment"] but allowed ids = ["cartonization"] only
    md = distill_concept(concept, docs, FakeLLM(), max_chars=1000, today="2026-06-29",
                         related_ids=["cartonization"])
    fm = yaml.safe_load(md.split("---")[1])
    assert fm["related"] == []


def test_distill_concept_bad_reply_returns_none():
    class Bad:
        def complete(self, system, user): return "garbage"
    assert distill_concept(Concept(id="x", title="X"), [Doc("a", "a", "t")], Bad(),
                           max_chars=10, today="2026-06-29") is None


def test_distill_concept_non_string_body_returns_none():
    """A non-string body value (e.g. a list) must return None, not raise."""
    class ListBodyLLM:
        def complete(self, system, user):
            return '{"title": "T", "description": "d", "tags": [], "related": [], "body": ["x"]}'
    assert distill_concept(Concept(id="x", title="X"), [Doc("a", "a", "t")], ListBodyLLM(),
                           max_chars=100, today="2026-06-29") is None

from hivegen.assign import assign_docs, classify_doc
from hivegen.load import Doc
from hivegen.taxonomy import Concept

CONCEPTS = [Concept(id="wave-template", title="Wave Template"),
            Concept(id="replenishment", title="Replenishment")]


class MapLLM:
    """Returns the JSON the assigner expects, keyed by which doc text it sees."""
    def complete(self, system, user):
        # Extract document section to avoid matching concept names in the list
        doc_section = user.split("DOCUMENT", 1)[1] if "DOCUMENT" in user else user
        if "exclude-me" in doc_section:
            return '{"concept_id": "exclude"}'
        if "replen" in doc_section:
            return '{"concept_id": "replenishment"}'
        return '{"concept_id": "wave-template"}'


def test_classify_doc_returns_concept_id():
    d = Doc("a.md", "a.md", "about replen triggers")
    assert classify_doc(d, CONCEPTS, MapLLM()) == "replenishment"


def test_assign_docs_groups_and_excludes():
    docs = [Doc("w.md", "w.md", "wave template stuff"),
            Doc("r.md", "r.md", "replen stuff"),
            Doc("x.md", "x.md", "exclude-me instance dump")]
    assignments, excluded = assign_docs(docs, CONCEPTS, MapLLM())
    assert assignments["wave-template"] == ["w.md"]
    assert assignments["replenishment"] == ["r.md"]
    assert excluded == ["x.md"]

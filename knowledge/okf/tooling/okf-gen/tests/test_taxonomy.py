from okfgen.load import Doc
from okfgen.taxonomy import Concept, load_taxonomy, propose_taxonomy, write_taxonomy


class FakeLLM:
    def __init__(self, reply): self._reply = reply
    def complete(self, system, user): return self._reply


def test_propose_taxonomy_parses_concepts():
    reply = ('{"concepts": [{"id": "wave-template", "title": "Wave Template", '
             '"description": "How waving is configured", "aliases": ["waving"]}]}')
    docs = [Doc("a.md", "a.md", "wave template text")]
    concepts = propose_taxonomy(docs, FakeLLM(reply))
    assert concepts == [Concept(id="wave-template", title="Wave Template",
                                description="How waving is configured", aliases=["waving"])]


def test_taxonomy_roundtrip(tmp_path):
    concepts = [Concept(id="replenishment", title="Replenishment")]
    p = tmp_path / "taxonomy.yaml"
    write_taxonomy(p, concepts)
    assert load_taxonomy(p) == concepts


def test_propose_taxonomy_bad_reply_returns_empty():
    assert propose_taxonomy([Doc("a", "a", "x")], FakeLLM("garbage")) == []

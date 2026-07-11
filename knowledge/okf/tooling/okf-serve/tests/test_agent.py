from okfserve.agent import _SELECT_SYS, _index_text, answer_question, select_ids


def test_select_prompt_carries_regime_rule():
    assert "mutually exclusive" in _SELECT_SYS.lower()
    assert "[ops]" in _SELECT_SYS and "[traditional]" in _SELECT_SYS


def test_select_prompt_carries_version_rule():
    assert "version-neutral" in _SELECT_SYS.lower()
    assert "prefer" in _SELECT_SYS.lower()

INDEX = [{"id": "pre-wave-process", "title": "Pre-Wave", "description": "preview wave"},
         {"id": "shipping-wave-major-minor-order", "title": "Major/Minor", "description": "m/n"}]


class SelectLLM:
    def __init__(self, reply): self._reply = reply
    def complete(self, system, user): return self._reply


def test_select_ids_parses_and_filters_unknown():
    llm = SelectLLM('{"card_ids": ["pre-wave-process", "bogus"]}')
    out = select_ids(INDEX, "pre-wave?", llm, known_ids={"pre-wave-process"})
    assert out == ["pre-wave-process"]


def test_select_ids_retries_then_empty():
    llm = SelectLLM("no json here")
    out = select_ids(INDEX, "q", llm, known_ids={"pre-wave-process"})
    assert out == []


CARD = """---
title: Pre-Wave
description: preview wave
related: []
sources:
- kind: wms-doc
  ref: pre-wave-fs.md
status: approved
---

Pre-wave selects picktickets and stops.
"""


class AnswerLLM:
    def complete(self, system, user):
        return "Pre-wave previews wave results [pre-wave-fs.md]."


def test_answer_question_progressive(tmp_path):
    (tmp_path / "pre-wave-process.md").write_text(CARD)
    sel = SelectLLM('{"card_ids": ["pre-wave-process"]}')
    out = answer_question(tmp_path, "what is pre-wave?",
                          select_llm=sel, answer_llm=AnswerLLM(), mode="progressive")
    assert out["selected_ids"] == ["pre-wave-process"]
    assert out["bundle_ids"] == ["pre-wave-process"]
    assert "pre-wave" in out["answer"].lower()
    assert out["mode"] == "progressive"


def test_answer_question_ceiling_loads_all(tmp_path):
    (tmp_path / "pre-wave-process.md").write_text(CARD)
    out = answer_question(tmp_path, "what is pre-wave?",
                          select_llm=None, answer_llm=AnswerLLM(), mode="ceiling")
    assert out["mode"] == "ceiling"
    assert out["bundle_ids"] == ["pre-wave-process"]


def test_index_text_shows_regime():
    line = _index_text([{"id": "a", "title": "A", "description": "d", "regime": "ops", "type": "concept"}])
    assert "[ops]" in line and "a:" in line


def test_index_text_shows_version():
    line = _index_text([{"id": "a", "title": "A", "description": "d",
                         "regime": None, "type": "concept", "version": ["2020"]}])
    assert "(v2020)" in line


def test_index_text_renders_product_tag():
    line = _index_text([{"id": "c", "title": "C", "description": "d", "product": "osci"}])
    assert "{osci}" in line


def test_select_sys_has_product_rule():
    assert "product" in _SELECT_SYS.lower()


from okfserve.agent import _ANSWER_SYS


def test_answer_sys_has_correction_precedence():
    s = _ANSWER_SYS.lower()
    assert "correction" in s and ("authoritative" in s or "override" in s)


def test_answer_excludes_corrections_from_selection(tmp_path, monkeypatch):
    from okfserve import agent
    (tmp_path / "wms").mkdir(); (tmp_path / "wms" / "corrections").mkdir()
    (tmp_path / "wms" / "c.md").write_text("---\ntitle: C\ntype: concept\nrelated: []\n---\n\nbody\n")
    (tmp_path / "wms" / "corrections" / "fix.md").write_text(
        "---\ntitle: Fix\ntype: correction\ncorrects: wms/c\nstatus: approved\n---\n\n## Correction\n\nfix\n")
    seen = {}
    class Sel:
        def complete(self, system, user):
            seen["known"] = user
            return '{"card_ids": ["wms/c"]}'
    class Ans:
        def complete(self, system, user): return "ok"
    res = agent.answer_question(tmp_path, "q?", select_llm=Sel(), answer_llm=Ans())
    # the correction id must NOT be offered to the selector...
    assert "wms/corrections/fix" not in seen["known"]
    # ...but it IS co-pulled into the bundle
    assert "wms/corrections/fix" in res["bundle_ids"]


def test_select_sys_has_client_rule():
    from okfserve.agent import _SELECT_SYS
    s = _SELECT_SYS.lower()
    assert "client" in s and "memory" in s


def test_answer_sys_has_memory_rule():
    from okfserve.agent import _ANSWER_SYS
    s = _ANSWER_SYS.lower()
    assert "memory" in s and "client" in s


def test_index_text_shows_client_memory_tag():
    from okfserve.agent import _index_text
    line = _index_text([{"id": "clients/alpha/memory/m", "title": "M", "description": "d",
                         "type": "memory", "client": "alpha"}])
    assert "<client:alpha>" in line


def test_answer_question_client_scoped_selection(tmp_path):
    from okfserve import agent
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    (concepts / "wms").mkdir(parents=True)
    (concepts / "wms" / "a.md").write_text("---\ntitle: A\ndescription: d\nrelated: []\n---\n\nbody\n")
    (clients / "alpha" / "memory").mkdir(parents=True)
    (clients / "alpha" / "memory" / "m.md").write_text(
        "---\ntitle: M\ndescription: d\ntype: memory\nclient: alpha\nrelated: []\n---\n\nalpha mem\n")
    seen = {}
    class Sel:
        def complete(self, system, user):
            seen["idx"] = user
            return '{"card_ids": ["clients/alpha/memory/m"]}'
    class Ans:
        def complete(self, system, user): return "ok"
    # in alpha scope: the memory id is offered to the selector and resolvable
    res = agent.answer_question(concepts, "q?", select_llm=Sel(), answer_llm=Ans(),
                                clients_dir=clients, client="alpha")
    assert "clients/alpha/memory/m" in seen["idx"]
    assert "clients/alpha/memory/m" in res["bundle_ids"]
    # no client scope: the memory id must NOT be offered to the selector
    seen.clear()
    agent.answer_question(concepts, "q?", select_llm=Sel(), answer_llm=Ans(), clients_dir=clients)
    assert "clients/alpha/memory/m" not in seen["idx"]

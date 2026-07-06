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

from okfserve.agent import answer_question, select_ids

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

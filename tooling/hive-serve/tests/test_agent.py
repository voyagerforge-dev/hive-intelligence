import pytest

from hiveserve.agent import _index_text, answer_question, select_ids

INDEX = [{"id": "pre-wave-process", "title": "Pre-Wave", "description": "preview wave"},
         {"id": "shipping-wave-major-minor-order", "title": "Major/Minor", "description": "m/n"}]


class SelectLLM:
    def __init__(self, reply):
        self._reply = reply
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        return self._reply


@pytest.mark.parametrize("rule", [
    "OPS and traditional are MUTUALLY EXCLUSIVE by site configuration",
    "PREFER cards for that release plus version-neutral (untagged) cards",
    "pick ONLY cards of that product plus any untagged (product-neutral) cards; never mix products",
    "Pick a client-memory card ONLY when the QUESTION is about that same client",
])
def test_selector_delivers_rules_index_and_question(rule):
    llm = SelectLLM('{"card_ids": ["pre-wave-process"]}')
    selected, select_empty = select_ids(INDEX, "pre-wave?", llm, known_ids={"pre-wave-process"})
    assert selected == ["pre-wave-process"]
    assert select_empty is False
    assert len(llm.calls) == 1
    system, user = llm.calls[0]
    assert rule in system
    assert user == (
        "INDEX:\n- pre-wave-process: Pre-Wave, preview wave\n"
        "- shipping-wave-major-minor-order: Major/Minor, m/n\n\nQUESTION: pre-wave?")


def test_select_ids_parses_and_filters_unknown():
    llm = SelectLLM('{"card_ids": ["pre-wave-process", "bogus"]}')
    out, select_empty = select_ids(INDEX, "pre-wave?", llm, known_ids={"pre-wave-process"})
    assert out == ["pre-wave-process"]
    assert select_empty is False


def test_select_ids_retries_then_empty():
    """Unusable output is a retrieval miss, not an absent measurement: the model spoke."""
    llm = SelectLLM("no json here")
    out, select_empty = select_ids(INDEX, "q", llm, known_ids={"pre-wave-process"})
    assert out == []
    assert select_empty is False


@pytest.mark.parametrize("replies", [[None, "no json here"], ["no json here", None]])
def test_select_ids_counts_a_row_as_empty_only_when_every_attempt_was_blank(replies):
    """Selection retries once, so the flag is per row, not per reply: if the model spoke on
    EITHER attempt the row is a retrieval miss `select_hit` measures honestly, not an
    absent measurement. Order must not matter - a reply is not un-said by a later silence."""
    class _Scripted:
        def __init__(self, replies):
            self.replies = list(replies)

        def complete(self, system, user):
            return self.replies.pop(0)

    out, select_empty = select_ids(INDEX, "q", _Scripted(replies),
                                   known_ids={"pre-wave-process"})
    assert out == []
    assert select_empty is False


def test_select_ids_reports_a_selector_that_returned_nothing():
    """A silent selector measured nothing. Scoring that as a miss is how a run reports
    a retrieval collapse it never observed, so the empty case must be distinguishable."""
    class _Silent:
        def complete(self, system, user): return None
    out, select_empty = select_ids(INDEX, "q", _Silent(), known_ids={"pre-wave-process"})
    assert out == []
    assert select_empty is True


CARD = """---
title: Pre-Wave
description: preview wave
related: []
sources:
- kind: widgets-doc
  ref: pre-wave-fs.md
status: approved
---

Pre-wave selects picktickets and stops.
"""


class AnswerLLM:
    def __init__(self):
        self.calls = []

    def complete(self, system, user):
        self.calls.append((system, user))
        return "Pre-wave previews wave results [pre-wave-fs.md]."


@pytest.mark.parametrize("mode", ["progressive", "ceiling"])
@pytest.mark.parametrize("rule", [
    "Answer the QUESTION using ONLY the provided knowledge cards",
    "A correction is AUTHORITATIVE: ground your answer in the corrected fact and note the correction",
    "Use it only for that client and never generalise it to core product behaviour or another client",
])
def test_answerer_delivers_rules_bundle_and_question(tmp_path, mode, rule):
    (tmp_path / "pre-wave-process.md").write_text(CARD)
    answerer = AnswerLLM()
    result = answer_question(
        tmp_path, "what is pre-wave?", mode=mode,
        select_llm=SelectLLM('{"card_ids": ["pre-wave-process"]}'), answer_llm=answerer)
    assert result["answer"] == "Pre-wave previews wave results [pre-wave-fs.md]."
    assert result["bundle_cards"] == {"pre-wave-process": CARD}
    assert len(answerer.calls) == 1
    system, user = answerer.calls[0]
    assert rule in system
    assert user == f"KNOWLEDGE CARDS:\n{CARD}\n\nQUESTION: what is pre-wave?"


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
    line = _index_text([{"id": "c", "title": "C", "description": "d", "product": "gadgets"}])
    assert "{gadgets}" in line


def test_answer_excludes_corrections_from_selection(tmp_path, monkeypatch):
    from hiveserve import agent
    (tmp_path / "widgets").mkdir(); (tmp_path / "widgets" / "corrections").mkdir()
    (tmp_path / "widgets" / "c.md").write_text("---\ntitle: C\ntype: concept\nrelated: []\n---\n\nbody\n")
    (tmp_path / "widgets" / "corrections" / "fix.md").write_text(
        "---\ntitle: Fix\ntype: correction\ncorrects: widgets/c\nstatus: approved\n---\n\n## Correction\n\nfix\n")
    seen = {}
    class Sel:
        def complete(self, system, user):
            seen["known"] = user
            return '{"card_ids": ["widgets/c"]}'
    class Ans:
        def complete(self, system, user): return "ok"
    res = agent.answer_question(tmp_path, "q?", select_llm=Sel(), answer_llm=Ans())
    # the correction id must NOT be offered to the selector...
    assert "widgets/corrections/fix" not in seen["known"]
    # ...but it IS co-pulled into the bundle
    assert "widgets/corrections/fix" in res["bundle_ids"]


def test_index_text_shows_client_memory_tag():
    from hiveserve.agent import _index_text
    line = _index_text([{"id": "clients/alpha/memory/m", "title": "M", "description": "d",
                         "type": "memory", "client": "alpha"}])
    assert "<client:alpha>" in line


def test_answer_question_client_scoped_selection(tmp_path):
    from hiveserve import agent
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    (concepts / "widgets").mkdir(parents=True)
    (concepts / "widgets" / "a.md").write_text("---\ntitle: A\ndescription: d\nrelated: []\n---\n\nbody\n")
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


def test_selector_prompt_carries_no_out_of_scope_issue_card(tmp_path):
    """Issue cards are client-scoped, and the selector's filter had drifted from the tool's.

    `tools.list_concepts` excludes `("memory", "issue")` together; this filter named
    `memory` alone, so every client's issue-card titles and descriptions went into every
    selector prompt whichever client was asking, and even when none was. On a measured
    corpus that was 2,295 rows and two thirds of a 215,000-token prompt of
    client-confidential text, sent to the model gateway on every question.

    Aligned, the prompt holds no issue row at all when no client is named, and only the
    asking client's own when one is - exactly what the catalogue tool offers.
    """
    from hiveserve import agent
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    (concepts / "widgets").mkdir(parents=True)
    (concepts / "widgets" / "a.md").write_text("---\ntitle: A\ndescription: d\nrelated: []\n---\n\nbody\n")
    for name in ("alpha", "acme"):
        (clients / name / "issues").mkdir(parents=True)
        (clients / name / "issues" / "slow-pick.md").write_text(
            f"---\ntitle: {name} slow pick\ndescription: picking is slow\ntype: issue\n"
            "related: []\n---\n\nissue\n")
    seen = {}

    class Sel:
        def complete(self, system, user):
            seen["idx"] = user
            return '{"card_ids": ["widgets/a"]}'

    class Ans:
        def complete(self, system, user): return "ok"

    def prompt_for(client):
        seen.clear()
        agent.answer_question(concepts, "q?", select_llm=Sel(), answer_llm=Ans(),
                              clients_dir=clients, client=client)
        return seen["idx"]

    unscoped = prompt_for(None)
    assert "widgets/a" in unscoped
    assert "clients/alpha/issues/slow-pick" not in unscoped
    assert "clients/acme/issues/slow-pick" not in unscoped

    scoped = prompt_for("alpha")
    assert "clients/alpha/issues/slow-pick" in scoped      # its own, as list_concepts offers
    assert "clients/acme/issues/slow-pick" not in scoped   # never another client's

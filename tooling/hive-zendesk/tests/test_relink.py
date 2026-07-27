"""Deriving concept links for journal entries that were written with `related: []`."""

import json

from hivezendesk.relink import (
    clear_links,
    confine_to_one_product,
    product_of,
    set_linked_by,
    set_product,
    allowed_products,
    apply_links,
    build_idf,
    load_targets,
    rerank,
    relink_cards,
    suggest,
    tokenize,
)

CONCEPT = """---
type: concept
title: Wave Allocation Process
---
body
"""

DBOBJECT = """---
type: dbobject
title: ALLOC_PARM
---
body
"""

CARD = """---
type: issue
title: FC Wave failed to release
description: A wave allocation did not release.
client: alpha
module: wave
related: []
tags:
- wave
routine: false
sources:
- kind: zendesk-ticket
  ref: '123'
status: distilled
---

## What happened

A wave did not release.

## How it closed

Reprocessed.
"""


def _targets(tmp_path):
    (tmp_path / "wms").mkdir(parents=True)
    (tmp_path / "wms" / "wave-allocation-process.md").write_text(CONCEPT)
    (tmp_path / "wms" / "ALLOC_PARM.md").write_text(DBOBJECT)
    return load_targets(tmp_path)


def test_tokenize_drops_stopwords_and_short_tokens():
    assert "wave" in tokenize("The wave is in a DC")
    for noise in ("the", "is", "in", "a"):
        assert noise not in tokenize("The wave is in a DC")


def test_load_targets_excludes_dbobject_cards(tmp_path):
    """A journal entry should point at behaviour, not at a raw table definition."""
    targets = _targets(tmp_path)
    assert "wms/wave-allocation-process" in targets
    assert "wms/ALLOC_PARM" not in targets


def test_suggest_finds_the_obvious_concept(tmp_path):
    targets = _targets(tmp_path)
    idf = build_idf(targets)
    hits = suggest("wave allocation did not release", targets, idf)
    assert hits == ["wms/wave-allocation-process"]


def test_suggest_returns_nothing_when_overlap_is_not_distinctive(tmp_path):
    """A wrong link is worse than no link: the skills tell readers to follow these."""
    targets = _targets(tmp_path)
    idf = build_idf(targets)
    assert suggest("printer jammed in the despatch bay", targets, idf) == []


def test_suggest_requires_more_than_one_shared_token(tmp_path):
    targets = _targets(tmp_path)
    idf = build_idf(targets)
    # "wave" alone is a single token and must not be enough to assert a link
    assert suggest("wave", targets, idf) == []


def test_apply_links_sets_frontmatter_and_see_also():
    out = apply_links(CARD, ["wms/wave-allocation-process"])
    assert "related:\n- wms/wave-allocation-process\n" in out
    assert "## See also\n\n- `wms/wave-allocation-process`" in out
    # everything else survives untouched
    assert "ref: '123'" in out and "routine: false" in out
    assert "## What happened\n\nA wave did not release." in out


def test_apply_links_is_idempotent():
    once = apply_links(CARD, ["wms/wave-allocation-process"])
    assert apply_links(once, ["wms/wave-allocation-process"]) == once


def test_apply_links_with_no_links_leaves_card_unchanged():
    assert apply_links(CARD, []) == CARD


def test_apply_links_replaces_an_existing_link_block():
    once = apply_links(CARD, ["wms/a"])
    twice = apply_links(once, ["wms/b"])
    assert "wms/a" not in twice
    assert "related:\n- wms/b\n" in twice
    assert twice.count("## See also") == 1


# --- rerank: the lexical shortlist is only a candidate set; the model decides ---------

class FakeLLM:
    """Returns whatever `reply` holds; records the prompts it was given."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        return self.reply


CANDS = ["wms/carton-lock-unlock", "wms/olpn-content-report"]


def test_rerank_keeps_only_ids_that_were_offered():
    """A model that invents an id would create a link to a card that does not exist."""
    llm = FakeLLM(json.dumps({"picks": ["wms/carton-lock-unlock", "wms/made-up-card"]}))
    assert rerank("lock added", "a lock was added", CANDS, {}, llm) == ["wms/carton-lock-unlock"]


def test_rerank_accepts_a_refusal():
    """Declining is the correct answer for the many entries with no real match."""
    llm = FakeLLM(json.dumps({"picks": []}))
    assert rerank("repairs", "some repairs", CANDS, {}, llm) == []


def test_rerank_fails_closed_on_unparsable_reply():
    """No link beats a guessed link - the skills tell readers to follow these."""
    llm = FakeLLM("I could not decide.")
    assert rerank("x", "y", CANDS, {}, llm) == []


def test_rerank_caps_the_number_of_links():
    llm = FakeLLM(json.dumps({"picks": CANDS + ["wms/a"]}))
    assert len(rerank("x", "y", CANDS + ["wms/a"], {}, llm)) <= 2


def test_rerank_makes_no_call_without_candidates():
    llm = FakeLLM(json.dumps({"picks": []}))
    assert rerank("x", "y", [], {}, llm) == []
    assert llm.calls == 0


# --- orchestration -------------------------------------------------------------------

def _corpus(tmp_path):
    con = tmp_path / "concepts" / "wms"
    con.mkdir(parents=True)
    (con / "wave-allocation-process.md").write_text(CONCEPT)
    (con / "ALLOC_PARM.md").write_text(DBOBJECT)
    d = tmp_path / "clients" / "alpha" / "issues"
    d.mkdir(parents=True)
    (d / "123-fc-wave.md").write_text(CARD)
    return d


def test_relink_cards_writes_the_model_choice(tmp_path):
    d = _corpus(tmp_path)
    llm = FakeLLM(json.dumps({"picks": ["wms/wave-allocation-process"]}))
    rep = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts", llm, workers=1)
    assert rep.linked == 1
    body = (d / "123-fc-wave.md").read_text()
    assert "related:\n- wms/wave-allocation-process\n" in body
    assert "## See also" in body


def test_relink_cards_dry_run_writes_nothing(tmp_path):
    d = _corpus(tmp_path)
    before = (d / "123-fc-wave.md").read_text()
    llm = FakeLLM(json.dumps({"picks": ["wms/wave-allocation-process"]}))
    rep = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts", llm,
                       workers=1, dry_run=True)
    assert rep.linked == 1
    assert (d / "123-fc-wave.md").read_text() == before


def test_relink_cards_leaves_declined_entries_untouched(tmp_path):
    d = _corpus(tmp_path)
    before = (d / "123-fc-wave.md").read_text()
    rep = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts",
                       FakeLLM(json.dumps({"picks": []})), workers=1)
    assert rep.linked == 0 and rep.declined == 1
    assert (d / "123-fc-wave.md").read_text() == before


# --- a decline must retract a stale link, not preserve it -----------------------------

LINKED_CARD = CARD.replace("related: []\n", "related:\n- osci/performance-tuning\n")


def test_clear_links_empties_frontmatter_and_drops_see_also():
    linked = apply_links(CARD, ["wms/wave-allocation-process"])
    out = clear_links(linked)
    assert "related: []" in out
    assert "## See also" not in out
    assert "## What happened" in out and "ref: '123'" in out


def test_clear_links_is_a_noop_on_an_already_empty_card():
    assert clear_links(CARD) == CARD


def test_declining_retracts_an_existing_link(tmp_path):
    """The old links came from slug matching that produced cross-product errors. A model
    that declines is saying no candidate fits, which counts against the old link too."""
    con = tmp_path / "concepts" / "wms"
    con.mkdir(parents=True)
    (con / "wave-allocation-process.md").write_text(CONCEPT)
    d = tmp_path / "clients" / "alpha" / "issues"
    d.mkdir(parents=True)
    (d / "123-fc-wave.md").write_text(LINKED_CARD)

    rep = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts",
                       FakeLLM(json.dumps({"picks": []})), workers=1)
    assert rep.cleared == 1
    body = (d / "123-fc-wave.md").read_text()
    assert "osci/performance-tuning" not in body
    assert "related: []" in body


def test_declining_does_not_rewrite_a_card_that_had_no_links(tmp_path):
    con = tmp_path / "concepts" / "wms"
    con.mkdir(parents=True)
    (con / "wave-allocation-process.md").write_text(CONCEPT)
    d = tmp_path / "clients" / "alpha" / "issues"
    d.mkdir(parents=True)
    (d / "123-fc-wave.md").write_text(CARD)
    rep = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts",
                       FakeLLM(json.dumps({"picks": []})), workers=1)
    assert rep.cleared == 0 and rep.declined == 1
    assert (d / "123-fc-wave.md").read_text() == CARD


# --- product facet: OKF mandates 0 cross-product bleed (docs/OKF-Pipeline.md) ---------

OSCI = """---
type: concept
product: osci
title: Database Performance Tuning
---
body
"""


def test_tokenize_folds_plurals():
    """`Dock Doors not clearing` must be able to match `dock-door-management`."""
    assert tokenize("doors")[0] == tokenize("door")[0]
    assert tokenize("waves")[0] == tokenize("wave")[0]
    # ...without mangling words that merely end in s
    assert "access" in tokenize("access")


def test_product_of_returns_the_owning_product():
    assert product_of("osci/performance-tuning") == "osci"
    assert product_of("wms/allocation-process") == "wms"


def test_links_are_confined_to_one_product():
    """Two picks from different products would be exactly the bleed OKF forbids."""
    assert confine_to_one_product(["osci/perf", "wms/alloc", "osci/other"]) == \
        ["osci/perf", "osci/other"]
    assert confine_to_one_product([]) == []


def test_set_product_rewrites_the_facet():
    out = set_product(CARD, "osci")
    assert "product: osci" in out and "product: wms" not in out
    assert "## What happened" in out


def test_relink_stamps_the_product_of_the_card_it_linked(tmp_path):
    (tmp_path / "concepts" / "osci").mkdir(parents=True)
    (tmp_path / "concepts" / "osci" / "performance-tuning.md").write_text(OSCI)
    d = tmp_path / "clients" / "alpha" / "issues"
    d.mkdir(parents=True)
    card = CARD.replace("title: FC Wave failed to release",
                        "title: Cognos database performance tuning slow")
    card = card.replace("description: A wave allocation did not release.",
                        "description: Cognos database performance was slow and needed tuning.")
    (d / "9-db.md").write_text(card)
    llm = FakeLLM(json.dumps({"picks": ["osci/performance-tuning"]}))
    rep = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts", llm, workers=1)
    assert rep.linked == 1
    body = (d / "9-db.md").read_text()
    assert "product: osci" in body
    assert "related:\n- osci/performance-tuning\n" in body


def test_skip_linked_leaves_already_linked_cards_alone(tmp_path):
    """The monthly run only needs to consider entries that have no link yet."""
    con = tmp_path / "concepts" / "wms"
    con.mkdir(parents=True)
    (con / "wave-allocation-process.md").write_text(CONCEPT)
    d = tmp_path / "clients" / "alpha" / "issues"
    d.mkdir(parents=True)
    (d / "1-linked.md").write_text(apply_links(CARD, ["wms/wave-allocation-process"]))
    (d / "2-bare.md").write_text(CARD)
    llm = FakeLLM(json.dumps({"picks": ["wms/wave-allocation-process"]}))
    rep = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts", llm,
                       workers=1, skip_linked=True)
    assert rep.scanned == 1 and rep.linked == 1
    assert llm.calls == 1


# --- a wrong product facet HIDES an entry, so it needs positive evidence --------------

def test_allowed_products_always_includes_wms():
    assert allowed_products("WMOS Application is down") == {"wms"}


def test_allowed_products_opens_up_on_distinctive_vocabulary():
    assert "osci" in allowed_products("Cognos Reports: unable to load view")
    assert "osci" in allowed_products("SCI data source for CPA")
    assert "labour-management" in allowed_products("payroll rollover incorrect")
    assert "slotting" in allowed_products("slotting run did not complete")


def test_allowed_products_ignores_wms_words_that_merely_resemble_a_product():
    """`pick slot` is WMS vocabulary; it must not reclassify the entry as Slotting."""
    assert allowed_products("Error pallets in PTS staging pick slot") == {"wms"}


def test_relink_does_not_reclassify_without_evidence(tmp_path):
    """A WMS ticket stamped `slotting` disappears when a consultant scopes to WMS."""
    (tmp_path / "concepts" / "slotting").mkdir(parents=True)
    (tmp_path / "concepts" / "slotting" / "direct-integration.md").write_text(
        CONCEPT.replace("product: osci", "product: slotting")
        .replace("Wave Allocation Process", "Direct Integration Application"))
    d = tmp_path / "clients" / "alpha" / "issues"
    d.mkdir(parents=True)
    (d / "5-down.md").write_text(
        CARD.replace("title: FC Wave failed to release", "title: WMOS Application is down")
            .replace("description: A wave allocation did not release.",
                     "description: The direct integration application was down."))
    llm = FakeLLM(json.dumps({"picks": ["slotting/direct-integration"]}))
    relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts", llm, workers=1)
    body = (d / "5-down.md").read_text()
    assert "product: slotting" not in body
    assert "slotting/direct-integration" not in body


def test_results_are_written_as_they_complete_not_at_the_end(tmp_path):
    """A 1h50m run with a single end-of-client flush loses everything if it dies."""
    con = tmp_path / "concepts" / "wms"
    con.mkdir(parents=True)
    (con / "wave-allocation-process.md").write_text(CONCEPT)
    d = tmp_path / "clients" / "alpha" / "issues"
    d.mkdir(parents=True)
    for i in range(3):
        (d / f"{i}-card.md").write_text(CARD)

    written: list[str] = []

    class WatchingLLM(FakeLLM):
        def complete(self, system, user):
            # by the time the 3rd card is asked for, earlier ones must already be on disk
            written.append(sorted(p.name for p in d.glob("*.md")
                                  if "wms/wave-allocation-process" in p.read_text()))
            return super().complete(system, user)

    relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts",
                 WatchingLLM(json.dumps({"picks": ["wms/wave-allocation-process"]})),
                 workers=1)
    assert written[-1], "no card was persisted before the final model call"



def test_set_linked_by_records_which_model_chose_the_links():
    """`model:` records the distiller. Links can come from a different model entirely,
    and without this there is no way to tell Qwen-chosen links from Opus-chosen ones."""
    out = set_linked_by(CARD, "openrouter/claude-opus-4-8")
    assert "linked_by: openrouter/claude-opus-4-8" in out
    assert "## What happened" in out
    # idempotent, and does not duplicate on a second pass
    assert set_linked_by(out, "openrouter/claude-opus-4-8") == out
    # a later run with a different model replaces it
    assert "linked_by: x" in set_linked_by(out, "x")
    assert out.count("linked_by:") == 1

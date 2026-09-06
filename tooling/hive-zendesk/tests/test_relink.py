"""Deriving concept links for journal entries that were written with `related: []`."""

import json

from hivezendesk.relink import (
    allowed_products,
    apply_links,
    build_idf,
    clear_links,
    confine_to_one_product,
    load_targets,
    product_of,
    relink_cards,
    rerank,
    set_linked_by,
    set_product,
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
    (tmp_path / "widgets").mkdir(parents=True)
    (tmp_path / "widgets" / "wave-allocation-process.md").write_text(CONCEPT)
    (tmp_path / "widgets" / "ALLOC_PARM.md").write_text(DBOBJECT)
    return load_targets(tmp_path)


def test_tokenize_drops_stopwords_and_short_tokens():
    assert "wave" in tokenize("The wave is in a DC")
    for noise in ("the", "is", "in", "a"):
        assert noise not in tokenize("The wave is in a DC")


def test_load_targets_excludes_dbobject_cards(tmp_path):
    """A journal entry should point at behaviour, not at a raw table definition."""
    targets = _targets(tmp_path)
    assert "widgets/wave-allocation-process" in targets
    assert "widgets/ALLOC_PARM" not in targets


def test_suggest_finds_the_obvious_concept(tmp_path):
    targets = _targets(tmp_path)
    idf = build_idf(targets)
    hits = suggest("wave allocation did not release", targets, idf)
    assert hits == ["widgets/wave-allocation-process"]


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
    out = apply_links(CARD, ["widgets/wave-allocation-process"])
    assert "related:\n- widgets/wave-allocation-process\n" in out
    assert "## See also\n\n- `widgets/wave-allocation-process`" in out
    # everything else survives untouched
    assert "ref: '123'" in out and "routine: false" in out
    assert "## What happened\n\nA wave did not release." in out


def test_apply_links_is_idempotent():
    once = apply_links(CARD, ["widgets/wave-allocation-process"])
    assert apply_links(once, ["widgets/wave-allocation-process"]) == once


def test_apply_links_with_no_links_leaves_card_unchanged():
    assert apply_links(CARD, []) == CARD


def test_apply_links_replaces_an_existing_link_block():
    once = apply_links(CARD, ["widgets/a"])
    twice = apply_links(once, ["widgets/b"])
    assert "widgets/a" not in twice
    assert "related:\n- widgets/b\n" in twice
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


CANDS = ["widgets/carton-lock-unlock", "widgets/olpn-content-report"]


def test_rerank_keeps_only_ids_that_were_offered():
    """A model that invents an id would create a link to a card that does not exist."""
    llm = FakeLLM(json.dumps({"picks": ["widgets/carton-lock-unlock", "widgets/made-up-card"]}))
    assert rerank("lock added", "a lock was added", CANDS, {}, llm) == ["widgets/carton-lock-unlock"]


def test_rerank_accepts_a_refusal():
    """Declining is the correct answer for the many entries with no real match."""
    llm = FakeLLM(json.dumps({"picks": []}))
    assert rerank("repairs", "some repairs", CANDS, {}, llm) == []


def test_rerank_fails_closed_on_unparsable_reply():
    """No link beats a guessed link - the skills tell readers to follow these."""
    llm = FakeLLM("I could not decide.")
    assert rerank("x", "y", CANDS, {}, llm) == []


def test_rerank_caps_the_number_of_links():
    llm = FakeLLM(json.dumps({"picks": CANDS + ["widgets/a"]}))
    assert len(rerank("x", "y", CANDS + ["widgets/a"], {}, llm)) <= 2


def test_rerank_makes_no_call_without_candidates():
    llm = FakeLLM(json.dumps({"picks": []}))
    assert rerank("x", "y", [], {}, llm) == []
    assert llm.calls == 0


# --- orchestration -------------------------------------------------------------------

def _corpus(tmp_path):
    con = tmp_path / "concepts" / "widgets"
    con.mkdir(parents=True)
    (con / "wave-allocation-process.md").write_text(CONCEPT)
    (con / "ALLOC_PARM.md").write_text(DBOBJECT)
    d = tmp_path / "clients" / "alpha" / "issues"
    d.mkdir(parents=True)
    (d / "123-fc-wave.md").write_text(CARD)
    return d


def test_relink_cards_writes_the_model_choice(tmp_path):
    d = _corpus(tmp_path)
    llm = FakeLLM(json.dumps({"picks": ["widgets/wave-allocation-process"]}))
    rep = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts", llm, workers=1)
    assert rep.linked == 1
    body = (d / "123-fc-wave.md").read_text()
    assert "related:\n- widgets/wave-allocation-process\n" in body
    assert "## See also" in body


UNRELATED_CARD = (CARD
                  .replace("title: FC Wave failed to release", "title: Label printer jammed")
                  .replace("description: A wave allocation did not release.",
                           "description: The label printer jammed while packing.")
                  .replace("module: wave", "module: packing")
                  .replace("- wave\n", "- printer\n")
                  .replace("ref: '123'", "ref: '124'"))


class ExplodingLLM:
    """A client that cannot be used. Any call is the failure the test is looking for."""

    model = "must-not-be-called"

    def complete(self, system, user):
        raise AssertionError("--dry-run called the rerank; a dry run must spend nothing")


def test_dry_run_calls_no_model_and_writes_nothing(tmp_path):
    """`--dry-run` is a no-call mode: a flag with that name must not spend money.

    It used to suppress the writes only, and still bought one rerank per shortlisted card.
    The exploding client is the assertion: any request at all fails the test.
    """
    d = _corpus(tmp_path)
    (d / "124-printer.md").write_text(UNRELATED_CARD)
    before = {p.name: p.read_text() for p in d.glob("*.md")}

    rep = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts",
                       ExplodingLLM(), workers=1, dry_run=True)

    assert {p.name: p.read_text() for p in d.glob("*.md")} == before
    # The model decides `linked`/`declined`, and it was never asked, so both stay 0.
    assert (rep.linked, rep.declined) == (0, 0)


def test_dry_run_reports_the_rerank_calls_a_real_run_would_make(tmp_path):
    """What a dry run is FOR: the bill, in the unit it is charged in.

    One rerank per shortlisted card, none for a card the lexical pass offers nothing for.
    Getting that unit wrong is otherwise only discovered on an invoice.
    """
    d = _corpus(tmp_path)
    (d / "124-printer.md").write_text(UNRELATED_CARD)

    rep = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts",
                       ExplodingLLM(), workers=1, dry_run=True)

    assert (rep.scanned, rep.shortlisted, rep.no_shortlist) == (2, 1, 1)


def test_shortlisted_counts_the_same_thing_in_a_real_run(tmp_path):
    """The dry run's costing number is only trustworthy if it means one call there too."""
    d = _corpus(tmp_path)
    (d / "124-printer.md").write_text(UNRELATED_CARD)
    llm = FakeLLM(json.dumps({"picks": ["widgets/wave-allocation-process"]}))

    rep = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts", llm, workers=1)

    assert rep.shortlisted == llm.calls == 1
    assert rep.shortlisted == rep.linked + rep.declined


def test_relink_cards_leaves_declined_entries_untouched(tmp_path):
    d = _corpus(tmp_path)
    before = (d / "123-fc-wave.md").read_text()
    rep = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts",
                       FakeLLM(json.dumps({"picks": []})), workers=1)
    assert rep.linked == 0 and rep.declined == 1
    assert (d / "123-fc-wave.md").read_text() == before


# --- a decline must retract a stale link, not preserve it -----------------------------

LINKED_CARD = CARD.replace("related: []\n", "related:\n- gadgets/performance-tuning\n")
STALE_UNRELATED_CARD = UNRELATED_CARD.replace(
    "related: []\n", "related:\n- gadgets/performance-tuning\n")


def test_clear_links_empties_frontmatter_and_drops_see_also():
    linked = apply_links(CARD, ["widgets/wave-allocation-process"])
    out = clear_links(linked)
    assert "related: []" in out
    assert "## See also" not in out
    assert "## What happened" in out and "ref: '123'" in out


def test_clear_links_is_a_noop_on_an_already_empty_card():
    assert clear_links(CARD) == CARD


def test_declining_retracts_an_existing_link(tmp_path):
    """The old links came from slug matching that produced cross-product errors. A model
    that declines is saying no candidate fits, which counts against the old link too."""
    con = tmp_path / "concepts" / "widgets"
    con.mkdir(parents=True)
    (con / "wave-allocation-process.md").write_text(CONCEPT)
    d = tmp_path / "clients" / "alpha" / "issues"
    d.mkdir(parents=True)
    (d / "123-fc-wave.md").write_text(LINKED_CARD)

    rep = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts",
                       FakeLLM(json.dumps({"picks": []})), workers=1)
    assert rep.cleared == 1
    body = (d / "123-fc-wave.md").read_text()
    assert "gadgets/performance-tuning" not in body
    assert "related: []" in body


def test_declining_does_not_rewrite_a_card_that_had_no_links(tmp_path):
    con = tmp_path / "concepts" / "widgets"
    con.mkdir(parents=True)
    (con / "wave-allocation-process.md").write_text(CONCEPT)
    d = tmp_path / "clients" / "alpha" / "issues"
    d.mkdir(parents=True)
    (d / "123-fc-wave.md").write_text(CARD)
    rep = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts",
                       FakeLLM(json.dumps({"picks": []})), workers=1)
    assert rep.cleared == 0 and rep.declined == 1
    assert (d / "123-fc-wave.md").read_text() == CARD


def test_dry_run_counts_a_model_free_retraction_without_performing_it(tmp_path):
    """A dry run's `cleared` counts only what needs no model, and still writes nothing.

    An entry the lexical pass offers nothing for is retracted without asking anything, so a
    dry run can count that one. The retraction that follows a DECLINE it cannot count, the
    decline being the model's answer - which makes `cleared` a floor under the real run's,
    exactly as docs/reference/hive-zendesk.md describes it. Both cards here carry a stale
    link; only the second is reachable without spending.
    """
    d = _corpus(tmp_path)
    (d / "123-fc-wave.md").write_text(LINKED_CARD)          # shortlisted: needs the model
    (d / "124-printer.md").write_text(STALE_UNRELATED_CARD)  # no shortlist: needs nothing
    before = {p.name: p.read_text() for p in d.glob("*.md")}

    dry = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts",
                       ExplodingLLM(), workers=1, dry_run=True)

    assert dry.cleared == 1
    assert {p.name: p.read_text() for p in d.glob("*.md")} == before

    real = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts",
                        FakeLLM(json.dumps({"picks": []})), workers=1)

    assert (real.cleared, real.declined) == (2, 1)
    assert dry.cleared < real.cleared
    assert not any("gadgets/performance-tuning" in p.read_text() for p in d.glob("*.md"))


# --- product facet: OKF mandates 0 cross-product bleed (docs/architecture/pipeline.md) ---------

GADGET_CARD = """---
type: concept
product: gadgets
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
    assert product_of("gadgets/performance-tuning") == "gadgets"
    assert product_of("widgets/allocation-process") == "widgets"


def test_links_are_confined_to_one_product():
    """Two picks from different products would be exactly the bleed OKF forbids."""
    assert confine_to_one_product(["gadgets/perf", "widgets/alloc", "gadgets/other"]) == \
        ["gadgets/perf", "gadgets/other"]
    assert confine_to_one_product([]) == []


def test_set_product_rewrites_the_facet():
    out = set_product(CARD, "gadgets")
    assert "product: gadgets" in out and "product: widgets" not in out
    assert "## What happened" in out


def test_relink_stamps_the_product_of_the_card_it_linked(tmp_path):
    (tmp_path / "concepts" / "gadgets").mkdir(parents=True)
    (tmp_path / "concepts" / "gadgets" / "performance-tuning.md").write_text(GADGET_CARD)
    d = tmp_path / "clients" / "alpha" / "issues"
    d.mkdir(parents=True)
    card = CARD.replace("title: FC Wave failed to release",
                        "title: Cognos database performance tuning slow")
    card = card.replace("description: A wave allocation did not release.",
                        "description: Cognos database performance was slow and needed tuning.")
    (d / "9-db.md").write_text(card)
    llm = FakeLLM(json.dumps({"picks": ["gadgets/performance-tuning"]}))
    rep = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts", llm, workers=1)
    assert rep.linked == 1
    body = (d / "9-db.md").read_text()
    assert "product: gadgets" in body
    assert "related:\n- gadgets/performance-tuning\n" in body


def test_skip_linked_leaves_already_linked_cards_alone(tmp_path):
    """The monthly run only needs to consider entries that have no link yet."""
    con = tmp_path / "concepts" / "widgets"
    con.mkdir(parents=True)
    (con / "wave-allocation-process.md").write_text(CONCEPT)
    d = tmp_path / "clients" / "alpha" / "issues"
    d.mkdir(parents=True)
    (d / "1-linked.md").write_text(apply_links(CARD, ["widgets/wave-allocation-process"]))
    (d / "2-bare.md").write_text(CARD)
    llm = FakeLLM(json.dumps({"picks": ["widgets/wave-allocation-process"]}))
    rep = relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts", llm,
                       workers=1, skip_linked=True)
    assert rep.scanned == 1 and rep.linked == 1
    assert llm.calls == 1


# --- a wrong product facet HIDES an entry, so it needs positive evidence --------------
#
# The vocabulary below is synthetic. Which products exist, and which words mark them, is
# one corpus's knowledge and lives in its profile; what the product owns is the rule that
# leaving the default requires positive evidence in the entry's own words.

from hivezendesk.profile import LinkingProfile

LINKING = LinkingProfile(
    default_product="core",
    product_markers={
        "reporting": {"cognos", "dashboard", "kpi"},
        "workforce": {"payroll", "roster", "timesheet"},
        "layout": {"sprockets"},
    },
)


def test_allowed_products_always_includes_the_default():
    assert allowed_products("Application is down", LINKING) == {"core"}


def test_allowed_products_opens_up_on_distinctive_vocabulary():
    assert "reporting" in allowed_products("Cognos reports will not load", LINKING)
    assert "workforce" in allowed_products("payroll rollover incorrect", LINKING)
    assert "layout" in allowed_products("sprockets run did not complete", LINKING)


def test_allowed_products_needs_a_marker_not_a_resemblance():
    """A word that merely looks related must not open a product up: a misfiled entry is
    invisible to anyone scoped to the product it actually belongs to."""
    out = allowed_products("report printing failed on the label printer", LINKING)
    assert out == {"core"}


def test_no_profile_means_do_not_confine_rather_than_permit_nothing():
    """None is "confinement is not configured". An empty set would mean "no product is
    permitted", which rejects every candidate and links nothing, and that is
    indistinguishable from a corpus that simply has no matching cards."""
    assert allowed_products("anything at all", LinkingProfile()) is None



def test_relink_does_not_reclassify_without_evidence(tmp_path):
    """A WIDGETS ticket stamped `sprockets` disappears when a consultant scopes to WIDGETS."""
    (tmp_path / "concepts" / "sprockets").mkdir(parents=True)
    (tmp_path / "concepts" / "sprockets" / "direct-integration.md").write_text(
        CONCEPT.replace("product: gadgets", "product: sprockets")
        .replace("Wave Allocation Process", "Direct Integration Application"))
    d = tmp_path / "clients" / "alpha" / "issues"
    d.mkdir(parents=True)
    (d / "5-down.md").write_text(
        CARD.replace("title: FC Wave failed to release", "title: BENCH Application is down")
            .replace("description: A wave allocation did not release.",
                     "description: The direct integration application was down."))
    llm = FakeLLM(json.dumps({"picks": ["sprockets/direct-integration"]}))
    # Confinement needs a vocabulary: the default product is `widgets`, and `sprockets` is only
    # permitted when the entry's own words say so. This entry's words do not.
    linking = LinkingProfile(default_product="widgets",
                             product_markers={"sprockets": {"sprockets"}})
    relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts", llm, workers=1,
                 linking=linking)
    body = (d / "5-down.md").read_text()
    assert "product: sprockets" not in body
    assert "sprockets/direct-integration" not in body


def test_results_are_written_as_they_complete_not_at_the_end(tmp_path):
    """A 1h50m run with a single end-of-client flush loses everything if it dies."""
    con = tmp_path / "concepts" / "widgets"
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
                                  if "widgets/wave-allocation-process" in p.read_text()))
            return super().complete(system, user)

    relink_cards(["alpha"], tmp_path / "clients", tmp_path / "concepts",
                 WatchingLLM(json.dumps({"picks": ["widgets/wave-allocation-process"]})),
                 workers=1)
    assert written[-1], "no card was persisted before the final model call"



def test_set_linked_by_records_which_model_chose_the_links():
    """`model:` records the distiller. Links can come from a different model entirely,
    and without this there is no way to tell Qwen-chosen links from Opus-chosen ones."""
    out = set_linked_by(CARD, "anthropic/claude-opus-4.8")
    assert "linked_by: anthropic/claude-opus-4.8" in out
    assert "## What happened" in out
    # idempotent, and does not duplicate on a second pass
    assert set_linked_by(out, "anthropic/claude-opus-4.8") == out
    # a later run with a different model replaces it
    assert "linked_by: x" in set_linked_by(out, "x")
    assert out.count("linked_by:") == 1

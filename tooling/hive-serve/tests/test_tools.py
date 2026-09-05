from hiveserve import tools

CARD = """---
title: Wave Replen
description: how replen feeds waves
related: []
sources: [widgets.md]
---
Body text.
"""


def _seed(tmp_path):
    (tmp_path / "wave-replen.md").write_text(CARD)
    return tmp_path


def test_list_concepts(tmp_path):
    d = _seed(tmp_path)
    idx = tools.list_concepts(d)
    # Lean rows: description is dropped so the 990-card catalogue does not blow the client
    # token cap. Use find_concepts for a topic search that returns descriptions.
    assert idx == [{"id": "wave-replen", "title": "Wave Replen", "type": "concept"}]
    assert "description" not in idx[0]   # dropped: it balloons the 990-card catalogue


def test_list_concepts_excludes_corrections(tmp_path):
    (tmp_path / "wave-replen.md").write_text(CARD)
    correction_dir = tmp_path / "corrections"
    correction_dir.mkdir()
    correction_dir.joinpath("wave-replen-fix.md").write_text("""---
title: Wave Replen Fix
description: correction to replen feeding
related: []
sources: [widgets.md]
type: correction
corrects: wave-replen
status: approved
---
Corrected body text.
""")
    idx = tools.list_concepts(tmp_path)
    ids = [c["id"] for c in idx]
    assert "wave-replen" in ids
    assert "corrections/wave-replen-fix" not in ids


def test_get_card_text_present_and_missing(tmp_path):
    d = _seed(tmp_path)
    assert "Body text." in tools.get_card_text(d, "wave-replen")
    assert "No card" in tools.get_card_text(d, "nope")


def test_resolve_cards(tmp_path):
    d = _seed(tmp_path)
    out = tools.resolve_cards(d, ["wave-replen"], depth=1)
    assert out["card_ids"] == ["wave-replen"]
    assert "Body text." in out["bundle"]


LINKED_A = """---
title: A
description: a
related: [b]
sources: [s.md]
---
AAAA body.
"""
LINKED_B = """---
title: B
description: b
related: []
sources: [s.md]
---
BBBB body.
"""


def test_resolve_cards_honors_max_chars(tmp_path):
    (tmp_path / "a.md").write_text(LINKED_A)
    (tmp_path / "b.md").write_text(LINKED_B)
    out = tools.resolve_cards(tmp_path, ["a"], depth=1, max_chars=1)
    assert out["card_ids"] == ["a"]      # first card always kept
    assert "b" in out["dropped"]          # linked card dropped by the char budget


def _client_world(tmp_path):
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    (concepts / "widgets").mkdir(parents=True)
    (concepts / "widgets" / "a.md").write_text("---\ntitle: A\ndescription: d\nproduct: widgets\n---\n\nbody\n")
    (clients / "alpha" / "memory").mkdir(parents=True)
    (clients / "alpha" / "memory" / "m.md").write_text(
        "---\ntitle: M\ndescription: d\ntype: memory\nclient: alpha\nproduct: widgets\n---\n\nmem\n")
    return concepts, clients


def test_list_concepts_client_scoped(tmp_path):
    from hiveserve import tools
    concepts, clients = _client_world(tmp_path)
    ids_none = {c["id"] for c in tools.list_concepts(concepts, clients, client=None)}
    assert ids_none == {"widgets/a"}                                 # no client -> no memory
    ids_alpha = {c["id"] for c in tools.list_concepts(concepts, clients, client="alpha")}
    assert ids_alpha == {"widgets/a", "clients/alpha/memory/m"}          # alpha sees its memory
    ids_acme = {c["id"] for c in tools.list_concepts(concepts, clients, client="acme")}
    assert ids_acme == {"widgets/a"}                                 # acme never sees alpha memory


def test_get_card_text_client_tree(tmp_path):
    from hiveserve import tools
    concepts, clients = _client_world(tmp_path)
    assert "mem" in tools.get_card_text(concepts, "clients/alpha/memory/m", clients)


def test_list_concepts_excludes_db_tier(tmp_path):
    (tmp_path / "wave-replen.md").write_text(CARD)
    dbdir = tmp_path / "db" / "tables"
    dbdir.mkdir(parents=True)
    dbdir.joinpath("T.md").write_text("""---
type: dbobject
kind: table
title: T
description: d
product: widgets
---
body
""")
    idx = tools.list_concepts(tmp_path)
    ids = [c["id"] for c in idx]
    assert "wave-replen" in ids
    assert "db/tables/T" not in ids
    assert "No card" not in tools.get_card_text(tmp_path, "db/tables/T")


# --- find_concepts: topic search so a broad question never dumps 990 cards ------------

C_ALLOC = """---
title: Allocation Process
description: how allocation assigns inventory to waves
related: []
---
body
"""
C_LABEL = """---
title: Label Printing
description: pallet and carton label formats
related: []
---
body
"""


def _seed_two(tmp_path):
    (tmp_path / "allocation-process.md").write_text(C_ALLOC)
    (tmp_path / "label-printing.md").write_text(C_LABEL)
    return tmp_path


def test_find_concepts_ranks_by_query_and_keeps_description(tmp_path):
    d = _seed_two(tmp_path)
    hits = tools.find_concepts(d, "allocation inventory")
    assert hits[0]["id"] == "allocation-process"
    assert hits[0]["description"] == "how allocation assigns inventory to waves"


def test_find_concepts_returns_nothing_for_no_match(tmp_path):
    d = _seed_two(tmp_path)
    assert tools.find_concepts(d, "yard trailer dock") == []


def test_find_concepts_respects_limit(tmp_path):
    d = _seed_two(tmp_path)
    assert len(tools.find_concepts(d, "label allocation", limit=1)) == 1


def test_find_concepts_empty_query_is_empty(tmp_path):
    d = _seed_two(tmp_path)
    assert tools.find_concepts(d, "   ") == []


# --- ranking: each behaviour the idf scorer replaced, pinned by name -------------------
#
# The old scorer counted how many raw whitespace-split query tokens appeared as substrings
# of `title + description + id`. On a measured 990-card corpus that put the right card in
# the top 20 for only 77.1% of 70 labelled questions; this scorer reaches 92.9% on the same
# questions with no question getting worse. Each test below is one of the four causes.

def _write(d, path, title, description, product=None):
    p = d / f"{path}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    prod = f"product: {product}\n" if product else ""
    p.write_text(f"---\ntitle: {title}\ndescription: {description}\n{prod}related: []\n---\nbody\n")


def test_find_concepts_trailing_question_mark_keeps_the_final_word(tmp_path):
    """A question's last word is usually its most specific one, and it carries the `?`.

    The two cards below differ only in which release they describe, so the release number
    is the whole answer. Splitting on whitespace made that final token `12?`, which matched
    nothing, leaving the two cards tied and the alphabet to pick the wrong one. Tokenising
    on runs of letters and digits recovers it. On a measured question set this single defect was enough to
    score a whole release-versioned set zero.
    """
    _write(tmp_path, "widgets/calibration-r11", "Calibration Routine",
           "the calibration routine in release 11")
    _write(tmp_path, "widgets/calibration-r12", "Calibration Routine",
           "the calibration routine in release 12")
    hits = tools.find_concepts(tmp_path, "How does the calibration routine work in release 12?")
    assert hits[0]["id"] == "widgets/calibration-r12"


def test_find_concepts_stopword_only_query_returns_nothing(tmp_path):
    """Function words carry no topic, so a query made only of them selects nothing.

    Under the old scorer this was the worst case: measured on a 990-card corpus, `a` matched
    990 cards and `in` 974, so a query of pure stopwords returned the whole corpus in
    alphabetical order.
    """
    _seed_two(tmp_path)
    assert tools.find_concepts(tmp_path, "what is it in the and for") == []


def test_find_concepts_common_word_does_not_match_inside_another_word(tmp_path):
    """`in` and `a` must not match by living inside a longer word.

    `t in hay` was substring containment, so `in` matched via "listing", `a` via almost
    anything, and `at` via "catalogue". Both halves of that are closed here: stopwords are
    dropped from the query, and whatever survives is matched as a whole word.
    """
    _write(tmp_path, "widgets/catalogue-listing", "Catalogue Listing",
           "activity definitions listing at the catalogue, and the report formats")
    # stopwords, and nothing else in the query: no card is selected on their account
    assert tools.find_concepts(tmp_path, "in a at and") == []
    # a non-stopword token still only matches whole words: `port` is not `report`
    assert tools.find_concepts(tmp_path, "port") == []
    assert [h["id"] for h in tools.find_concepts(tmp_path, "report")] == ["widgets/catalogue-listing"]


def test_find_concepts_rare_term_outranks_common_term(tmp_path):
    """One point per distinct token present made a ubiquitous word worth as much as a rare one.

    Here five cards share a common word and one card holds a rare one. Both candidates match
    exactly one query term, so the old scorer tied them and let the alphabet decide - which
    put the rare-term card last. Inverse document frequency puts it first.
    """
    for i in range(5):
        _write(tmp_path, f"widgets/a-config-{i}", f"Configuration {i}", "configuration settings")
    _write(tmp_path, "widgets/z-telemetry", "Telemetry", "telemetry rules")
    hits = tools.find_concepts(tmp_path, "configuration telemetry")
    assert hits[0]["id"] == "widgets/z-telemetry"


def test_find_concepts_slug_restating_the_query_ranks_first(tmp_path):
    """A card id is slug words, and they are weighed exactly like title words.

    The two cards below carry the same title and the same description, so the only thing
    separating them is the slug - which in one of them restates the query. The old scorer
    asked only whether a token appeared somewhere in the joined text, never how often or how
    distinctively, and cards in exactly this position ranked dozens of places down. Note
    also that the losing id sorts first alphabetically, so passing this means the slug earned
    the position rather than inheriting it from the tie-break.
    """
    _write(tmp_path, "widgets/carton-label-priority-rules", "Priority Rules",
           "the rules that order work")
    _write(tmp_path, "widgets/aaa-other-rules", "Priority Rules",
           "the rules that order work")
    hits = tools.find_concepts(tmp_path, "carton label priority rules")
    assert [h["id"] for h in hits] == [
        "widgets/carton-label-priority-rules", "widgets/aaa-other-rules"]


def test_find_concepts_return_shape_and_product_filter_unchanged(tmp_path):
    """Both doors and the skills read these four keys; the ranking changed, they did not."""
    _write(tmp_path, "widgets/allocation-process", "Allocation Process",
           "how allocation assigns inventory to waves", product="widgets")
    _write(tmp_path, "gadgets/allocation-deliverables", "Allocation Deliverables",
           "allocation deliverables for gadgets", product="gadgets")
    hits = tools.find_concepts(tmp_path, "allocation")
    assert {h["id"] for h in hits} == {"widgets/allocation-process", "gadgets/allocation-deliverables"}
    assert set(hits[0]) == {"id", "title", "product", "description"}
    scoped = tools.find_concepts(tmp_path, "allocation", product="gadgets")
    assert [h["id"] for h in scoped] == ["gadgets/allocation-deliverables"]
    assert scoped[0]["description"] == "allocation deliverables for gadgets"
    assert tools.find_concepts(tmp_path, "allocation", limit=1) == hits[:1]


def test_find_concepts_ties_still_break_by_id(tmp_path):
    """Two cards that say the same things stay in a stable, id-ordered sequence."""
    _write(tmp_path, "widgets/b-twin", "Twin", "identical wording for the tie test")
    _write(tmp_path, "widgets/a-twin", "Twin", "identical wording for the tie test")
    assert [h["id"] for h in tools.find_concepts(tmp_path, "twin wording")] == [
        "widgets/a-twin", "widgets/b-twin"]


def test_find_concepts_finds_a_card_written_in_a_non_latin_script(tmp_path):
    """A Japanese query must still reach its card; an ASCII-only tokeniser returned nothing.

    Japanese is written without spaces and nothing here segments words, so a term is a run
    of characters between separators - which is what the query below is. Given that, the
    scorer behaves exactly as it does in English: the card whose title and description carry
    the run is selected and the card that shares none of it is not.
    """
    _write(tmp_path, "widgets/shukka-wave", "出荷ウェーブ", "出荷ウェーブ の 割当 ルール")
    _write(tmp_path, "widgets/label-printing", "ラベル印刷", "パレット の ラベル 形式")
    assert [h["id"] for h in tools.find_concepts(tmp_path, "出荷ウェーブ")] == ["widgets/shukka-wave"]

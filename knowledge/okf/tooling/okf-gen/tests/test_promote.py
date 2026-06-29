from okfgen.promote import parse_frontmatter, promote, validate_card

CARD_OK = ("---\ntype: concept\ntitle: Wave\ndescription: d\ntags: [w]\nresource: wmos\n"
           "sources: []\nrelated: [replenishment]\ndistilled_at: 2026-06-29\nstatus: approved\n---\n\nBody\n")
CARD_DRAFT = CARD_OK.replace("status: approved", "status: draft")
CARD_BADLINK = CARD_OK.replace("related: [replenishment]", "related: [does-not-exist]")


def test_parse_frontmatter():
    assert parse_frontmatter(CARD_OK)["title"] == "Wave"


def test_validate_card_ok_and_badlink():
    assert validate_card(CARD_OK, {"wave", "replenishment"}) == []
    errs = validate_card(CARD_BADLINK, {"wave", "replenishment"})
    assert any("does-not-exist" in e for e in errs)


def test_promote_moves_only_approved(tmp_path):
    drafts = tmp_path / "drafts"
    concepts = tmp_path / "concepts"
    drafts.mkdir()
    concepts.mkdir()
    (drafts / "wave.md").write_text(CARD_OK)
    (drafts / "replenishment.md").write_text(CARD_DRAFT)
    promoted, invalid = promote(drafts, concepts)
    assert promoted == ["wave.md"]
    assert (concepts / "wave.md").exists()
    assert (drafts / "replenishment.md").exists()  # draft left in place
    assert invalid == {}

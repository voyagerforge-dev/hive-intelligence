from hivegen.promote import parse_frontmatter, promote, validate_card

CARD_OK = ("---\ntype: concept\ntitle: Wave\ndescription: d\ntags: [w]\nresource: wmos\n"
           "sources: []\nrelated: [osci/replenishment]\ndistilled_at: 2026-06-29\nstatus: approved\n---\n\nBody\n")
CARD_DRAFT = CARD_OK.replace("status: approved", "status: draft")
CARD_BADLINK = CARD_OK.replace("related: [osci/replenishment]", "related: [does-not-exist]")
CARD_NOREL = CARD_OK.replace("related: [osci/replenishment]", "related: []")


def test_parse_frontmatter():
    assert parse_frontmatter(CARD_OK)["title"] == "Wave"


def test_validate_card_ok_and_badlink():
    assert validate_card(CARD_OK, {"wave", "osci/replenishment"}) == []
    errs = validate_card(CARD_BADLINK, {"wave", "osci/replenishment"})
    assert any("does-not-exist" in e for e in errs)


def test_validate_card_missing_key():
    """Removing a required frontmatter key must produce an error mentioning that key."""
    card_missing_type = CARD_OK.replace("type: concept\n", "")
    errs = validate_card(card_missing_type, {"wave", "osci/replenishment"})
    assert errs  # non-empty list
    assert any("type" in e for e in errs)


def test_promote_moves_only_approved(tmp_path):
    drafts = tmp_path / "drafts"
    concepts = tmp_path / "concepts"
    drafts.mkdir()
    concepts.mkdir()
    (drafts / "wave.md").write_text(CARD_OK)  # related: [osci/replenishment]
    (drafts / "replenishment.md").write_text(CARD_DRAFT)  # sibling draft supplies prospective id
    promoted, invalid = promote(drafts, concepts, "osci")
    assert promoted == ["wave.md"]
    assert (concepts / "osci" / "wave.md").exists()
    assert (drafts / "replenishment.md").exists()  # draft left in place (not approved)
    assert invalid == {}


def test_promote_writes_into_product_subfolder(tmp_path):
    drafts = tmp_path / "drafts"
    concepts = tmp_path / "concepts"
    drafts.mkdir()
    concepts.mkdir()
    (drafts / "wave.md").write_text(CARD_NOREL)
    promoted, invalid = promote(drafts, concepts, "slotting")
    assert promoted == ["wave.md"]
    assert (concepts / "slotting" / "wave.md").exists()
    assert not (concepts / "wave.md").exists()  # not flat, namespaced under product
    assert invalid == {}


def test_promote_does_not_overwrite_existing_card(tmp_path):
    """Overwrite guard: an existing card at the destination path blocks promotion."""
    drafts = tmp_path / "drafts"
    concepts = tmp_path / "concepts"
    drafts.mkdir()
    concepts.mkdir()
    dest_dir = concepts / "osci"
    dest_dir.mkdir()
    (dest_dir / "wave.md").write_text("---\ntitle: Existing\n---\n\nalready here\n")
    (drafts / "wave.md").write_text(CARD_NOREL)
    promoted, invalid = promote(drafts, concepts, "osci")
    assert promoted == []
    assert "wave.md" in invalid
    assert any("overwrite" in e for e in invalid["wave.md"])
    assert (dest_dir / "wave.md").read_text() == "---\ntitle: Existing\n---\n\nalready here\n"
    assert (drafts / "wave.md").exists()  # draft preserved, not consumed


def test_promote_known_ids_include_prospective_product_path(tmp_path):
    """A draft's `related` link to another draft in the same batch must validate against
    that draft's PROSPECTIVE post-promotion path id (product/stem), not its bare stem."""
    drafts = tmp_path / "drafts"
    concepts = tmp_path / "concepts"
    drafts.mkdir()
    concepts.mkdir()
    (drafts / "wave.md").write_text(CARD_OK)  # related: [osci/replenishment]
    (drafts / "replenishment.md").write_text(
        CARD_OK.replace("title: Wave", "title: Replenishment")
        .replace("related: [osci/replenishment]", "related: []"))
    promoted, invalid = promote(drafts, concepts, "osci")
    assert set(promoted) == {"wave.md", "replenishment.md"}
    assert invalid == {}
    assert (concepts / "osci" / "wave.md").exists()
    assert (concepts / "osci" / "replenishment.md").exists()

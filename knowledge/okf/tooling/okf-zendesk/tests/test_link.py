from okfzendesk.link import load_card_ids, resolve_related


def test_load_card_ids_walks_markdown(tmp_path):
    (tmp_path / "wms" / "allocation").mkdir(parents=True)
    (tmp_path / "wms" / "allocation" / "wave-replen-lag.md").write_text("---\ntype: concept\n---\n")
    (tmp_path / "wms" / "index.md").write_text("ignored")
    ids = load_card_ids(tmp_path)
    assert "wms/allocation/wave-replen-lag" in ids
    assert "wms/index" not in ids


def test_resolve_keeps_only_real_ids():
    ids = {"wms/allocation/wave-replen-lag"}
    out = resolve_related(["wms/allocation/wave-replen-lag", "wms/made/up"], ids)
    assert out == ["wms/allocation/wave-replen-lag"]


def test_resolve_matches_on_trailing_slug():
    ids = {"wms/allocation/wave-replen-lag"}
    assert resolve_related(["wave-replen-lag"], ids) == ["wms/allocation/wave-replen-lag"]


def test_resolve_is_deduped_and_ordered():
    ids = {"a/b", "c/d"}
    assert resolve_related(["c/d", "a/b", "c/d"], ids) == ["a/b", "c/d"]


def test_resolve_of_nothing_is_empty():
    assert resolve_related([], {"a/b"}) == []

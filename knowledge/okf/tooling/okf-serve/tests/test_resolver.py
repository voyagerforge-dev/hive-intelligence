from okfserve.resolver import get_card, load_index, parse_frontmatter, resolve

CARD_A = """---
title: Alpha
description: the alpha card
related:
- beta
- ghost
sources:
- kind: wms-doc
  ref: a.md
status: approved
---

Alpha body.
"""

CARD_B = """---
title: Beta
description: the beta card
related:
- gamma
sources: []
status: approved
---

Beta body.
"""

CARD_G = """---
title: Gamma
description: the gamma card
related: []
sources: []
status: approved
---

Gamma body.
"""


def _write(tmp_path):
    (tmp_path / "alpha.md").write_text(CARD_A)
    (tmp_path / "beta.md").write_text(CARD_B)
    (tmp_path / "gamma.md").write_text(CARD_G)
    return tmp_path


def test_parse_frontmatter():
    fm = parse_frontmatter(CARD_A)
    assert fm["title"] == "Alpha"
    assert fm["related"] == ["beta", "ghost"]


def test_load_index_sorted(tmp_path):
    _write(tmp_path)
    idx = load_index(tmp_path)
    assert [c["id"] for c in idx] == ["alpha", "beta", "gamma"]
    assert idx[0]["description"] == "the alpha card"


def test_get_card_present_and_absent(tmp_path):
    _write(tmp_path)
    assert "Alpha body." in get_card(tmp_path, "alpha")
    assert get_card(tmp_path, "nope") is None


def test_resolve_follows_related_to_depth_and_tolerates_broken(tmp_path):
    _write(tmp_path)
    out = resolve(tmp_path, ["alpha"], depth=1, max_cards=8)
    # depth 1 from alpha -> beta (ghost is broken, skipped); gamma is depth 2, excluded
    assert out["card_ids"] == ["alpha", "beta"]
    assert "ghost" not in out["card_ids"]
    assert "Alpha body." in out["bundle"] and "Beta body." in out["bundle"]


def test_resolve_depth_two_reaches_gamma(tmp_path):
    _write(tmp_path)
    out = resolve(tmp_path, ["alpha"], depth=2, max_cards=8)
    assert out["card_ids"] == ["alpha", "beta", "gamma"]


def test_resolve_caps_and_records_dropped(tmp_path):
    _write(tmp_path)
    out = resolve(tmp_path, ["alpha"], depth=2, max_cards=2)
    assert out["card_ids"] == ["alpha", "beta"]
    assert out["dropped"] == ["gamma"]


def test_resolve_max_chars_caps_and_records_dropped(tmp_path):
    _write(tmp_path)  # alpha->beta(->gamma at depth2); cards ~ small
    # tiny budget keeps only the first card, rest dropped
    out = resolve(tmp_path, ["alpha"], depth=1, max_cards=8, max_chars=1)
    assert out["card_ids"] == ["alpha"]
    assert "beta" in out["dropped"]


def test_parse_frontmatter_non_dict_returns_empty():
    assert parse_frontmatter("---\njust a string\n---\nbody") == {}


def test_load_index_includes_regime_and_type(tmp_path):
    (tmp_path / "x.md").write_text(
        "---\ntitle: X\ndescription: d\ntype: concept\nregime: ops\n---\nbody\n")
    idx = load_index(tmp_path)
    assert idx[0]["regime"] == "ops" and idx[0]["type"] == "concept"


def test_load_index_includes_version(tmp_path):
    (tmp_path / "v.md").write_text(
        "---\ntitle: V\ndescription: d\nversion:\n- '2020'\n---\nbody\n")
    idx = load_index(tmp_path)
    assert idx[0]["version"] == ["2020"]


OPS = "---\ntitle: OPS\ndescription: ops card\nregime: ops\nrelated:\n- trad\n---\nOPS body.\n"
TRAD = "---\ntitle: Trad\ndescription: trad card\nregime: traditional\nrelated: []\n---\nTrad body.\n"


def test_resolve_guards_cross_regime_expansion(tmp_path):
    (tmp_path / "ops.md").write_text(OPS)
    (tmp_path / "trad.md").write_text(TRAD)
    out = resolve(tmp_path, ["ops"], depth=1, max_cards=8)
    assert out["card_ids"] == ["ops"]            # trad is a cross-regime neighbour → not expanded
    assert "Trad body." not in out["bundle"]     # trad's own content never loaded


def test_resolve_still_honours_explicit_cross_regime_seed(tmp_path):
    (tmp_path / "ops.md").write_text(OPS)
    (tmp_path / "trad.md").write_text(TRAD)
    out = resolve(tmp_path, ["ops", "trad"], depth=1, max_cards=8)
    assert set(out["card_ids"]) == {"ops", "trad"}  # explicit seeds always loaded


# regression: a neighbour guarded out from a cross-regime parent must stay reachable
# via a legitimate same-regime parent in the same traversal (order-independent).
OPS2 = "---\ntitle: Ops2\ndescription: ops\nregime: ops\nrelated:\n- shared\n---\nOps2 body.\n"
TRAD2 = "---\ntitle: Trad2\ndescription: trad\nregime: traditional\nrelated:\n- shared\n---\nTrad2 body.\n"
SHARED = "---\ntitle: Shared\ndescription: shared trad\nregime: traditional\nrelated: []\n---\nShared body.\n"


def test_resolve_guarded_neighbour_still_reachable_via_same_regime_parent(tmp_path):
    (tmp_path / "ops2.md").write_text(OPS2)      # processed first; would guard-out 'shared'
    (tmp_path / "trad2.md").write_text(TRAD2)    # same regime as 'shared' → must reach it
    (tmp_path / "shared.md").write_text(SHARED)
    out = resolve(tmp_path, ["ops2", "trad2"], depth=1, max_cards=8)
    assert "shared" in out["card_ids"]
    assert "Shared body." in out["bundle"]


def test_load_index_surfaces_product(tmp_path):
    from okfserve.resolver import load_index
    (tmp_path / "c.md").write_text(
        "---\ntitle: C\ndescription: d\nproduct: osci\nversion: ['2020']\n---\n\nbody\n")
    idx = {c["id"]: c for c in load_index(tmp_path)}
    assert idx["c"]["product"] == "osci"


def test_load_index_flat_card_id_is_stem(tmp_path):
    """A card directly in concepts_dir (no subfolder) keeps id = stem (flat-layout backcompat)."""
    (tmp_path / "omni-framework.md").write_text(
        "---\ntitle: Omni\ndescription: d\n---\n\nbody\n")
    idx = {c["id"]: c for c in load_index(tmp_path)}
    assert "omni-framework" in idx


def test_load_index_subfolder_card_id_is_path(tmp_path):
    """A card inside a product subfolder gets a path id: <subfolder>/<stem>."""
    sub = tmp_path / "osci"
    sub.mkdir()
    (sub / "omni-framework.md").write_text(
        "---\ntitle: Omni\ndescription: d\n---\n\nbody\n")
    idx = {c["id"]: c for c in load_index(tmp_path)}
    assert "osci/omni-framework" in idx
    assert idx["osci/omni-framework"]["title"] == "Omni"


def test_load_index_skips_reserved_files_at_any_level(tmp_path):
    sub = tmp_path / "osci"
    sub.mkdir()
    (tmp_path / "index.md").write_text("---\ntitle: I\ndescription: d\n---\n\nbody\n")
    (tmp_path / "log.md").write_text("---\ntitle: L\ndescription: d\n---\n\nbody\n")
    (sub / "index.md").write_text("---\ntitle: I2\ndescription: d\n---\n\nbody\n")
    (sub / "log.md").write_text("---\ntitle: L2\ndescription: d\n---\n\nbody\n")
    (sub / "real.md").write_text("---\ntitle: Real\ndescription: d\n---\n\nbody\n")
    ids = {c["id"] for c in load_index(tmp_path)}
    assert ids == {"osci/real"}


def test_get_card_by_path_id(tmp_path):
    sub = tmp_path / "osci"
    sub.mkdir()
    (sub / "omni-framework.md").write_text(
        "---\ntitle: Omni\ndescription: d\n---\n\nOmni body.\n")
    assert "Omni body." in get_card(tmp_path, "osci/omni-framework")


def test_resolve_follows_related_across_subfolders(tmp_path):
    sub = tmp_path / "osci"
    sub.mkdir()
    (sub / "alpha.md").write_text(
        "---\ntitle: A\ndescription: d\nrelated:\n- osci/beta\n---\n\nAlpha body.\n")
    (sub / "beta.md").write_text(
        "---\ntitle: B\ndescription: d\nrelated: []\n---\n\nBeta body.\n")
    out = resolve(tmp_path, ["osci/alpha"], depth=1, max_cards=8)
    assert out["card_ids"] == ["osci/alpha", "osci/beta"]
    assert "Beta body." in out["bundle"]


def test_get_card_rejects_traversal(tmp_path):
    from okfserve.resolver import get_card
    (tmp_path / "wms").mkdir()
    (tmp_path / "wms" / "a.md").write_text("---\ntitle: A\n---\n\nbody\n")
    (tmp_path.parent / "secret.md").write_text("secret")
    assert get_card(tmp_path, "wms/a") is not None          # valid path-id works
    assert get_card(tmp_path, "../secret") is None           # traversal blocked
    assert get_card(tmp_path, "../../etc/passwd") is None


def test_load_index_surfaces_corrects_status(tmp_path):
    from okfserve.resolver import load_index
    (tmp_path / "wms").mkdir()
    (tmp_path / "wms" / "corrections").mkdir()
    (tmp_path / "wms" / "c.md").write_text("---\ntitle: C\ntype: concept\n---\n\nbody\n")
    (tmp_path / "wms" / "corrections" / "fix.md").write_text(
        "---\ntitle: Fix\ntype: correction\ncorrects: wms/c\nstatus: approved\n---\n\n## Correction\n\nx\n")
    idx = {c["id"]: c for c in load_index(tmp_path)}
    assert idx["wms/c"]["corrects"] is None
    assert idx["wms/corrections/fix"]["type"] == "correction"
    assert idx["wms/corrections/fix"]["corrects"] == "wms/c"
    assert idx["wms/corrections/fix"]["status"] == "approved"


def test_corrections_by_target_active_only():
    from okfserve.resolver import corrections_by_target
    index = [
        {"id": "wms/c", "type": "concept"},
        {"id": "wms/corrections/a", "type": "correction", "corrects": "wms/c", "status": "approved"},
        {"id": "wms/corrections/b", "type": "correction", "corrects": "wms/c", "status": "superseded"},
    ]
    assert corrections_by_target(index) == {"wms/c": ["wms/corrections/a"]}

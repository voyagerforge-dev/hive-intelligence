from hiveserve.resolver import get_card, load_index, parse_frontmatter, resolve

CARD_A = """---
title: Alpha
description: the alpha card
related:
- beta
- ghost
sources:
- kind: widgets-doc
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
    from hiveserve.resolver import load_index
    (tmp_path / "c.md").write_text(
        "---\ntitle: C\ndescription: d\nproduct: gadgets\nversion: ['2020']\n---\n\nbody\n")
    idx = {c["id"]: c for c in load_index(tmp_path)}
    assert idx["c"]["product"] == "gadgets"


def test_load_index_flat_card_id_is_stem(tmp_path):
    """A card directly in concepts_dir (no subfolder) keeps id = stem (flat-layout backcompat)."""
    (tmp_path / "omni-framework.md").write_text(
        "---\ntitle: Omni\ndescription: d\n---\n\nbody\n")
    idx = {c["id"]: c for c in load_index(tmp_path)}
    assert "omni-framework" in idx


def test_load_index_subfolder_card_id_is_path(tmp_path):
    """A card inside a product subfolder gets a path id: <subfolder>/<stem>."""
    sub = tmp_path / "gadgets"
    sub.mkdir()
    (sub / "omni-framework.md").write_text(
        "---\ntitle: Omni\ndescription: d\n---\n\nbody\n")
    idx = {c["id"]: c for c in load_index(tmp_path)}
    assert "gadgets/omni-framework" in idx
    assert idx["gadgets/omni-framework"]["title"] == "Omni"


def test_load_index_skips_reserved_files_at_any_level(tmp_path):
    sub = tmp_path / "gadgets"
    sub.mkdir()
    (tmp_path / "index.md").write_text("---\ntitle: I\ndescription: d\n---\n\nbody\n")
    (tmp_path / "log.md").write_text("---\ntitle: L\ndescription: d\n---\n\nbody\n")
    (sub / "index.md").write_text("---\ntitle: I2\ndescription: d\n---\n\nbody\n")
    (sub / "log.md").write_text("---\ntitle: L2\ndescription: d\n---\n\nbody\n")
    (sub / "real.md").write_text("---\ntitle: Real\ndescription: d\n---\n\nbody\n")
    ids = {c["id"] for c in load_index(tmp_path)}
    assert ids == {"gadgets/real"}


def test_get_card_by_path_id(tmp_path):
    sub = tmp_path / "gadgets"
    sub.mkdir()
    (sub / "omni-framework.md").write_text(
        "---\ntitle: Omni\ndescription: d\n---\n\nOmni body.\n")
    assert "Omni body." in get_card(tmp_path, "gadgets/omni-framework")


def test_resolve_follows_related_across_subfolders(tmp_path):
    sub = tmp_path / "gadgets"
    sub.mkdir()
    (sub / "alpha.md").write_text(
        "---\ntitle: A\ndescription: d\nrelated:\n- gadgets/beta\n---\n\nAlpha body.\n")
    (sub / "beta.md").write_text(
        "---\ntitle: B\ndescription: d\nrelated: []\n---\n\nBeta body.\n")
    out = resolve(tmp_path, ["gadgets/alpha"], depth=1, max_cards=8)
    assert out["card_ids"] == ["gadgets/alpha", "gadgets/beta"]
    assert "Beta body." in out["bundle"]


def test_get_card_rejects_traversal(tmp_path):
    from hiveserve.resolver import get_card
    (tmp_path / "widgets").mkdir()
    (tmp_path / "widgets" / "a.md").write_text("---\ntitle: A\n---\n\nbody\n")
    (tmp_path.parent / "secret.md").write_text("secret")
    assert get_card(tmp_path, "widgets/a") is not None          # valid path-id works
    assert get_card(tmp_path, "../secret") is None           # traversal blocked
    assert get_card(tmp_path, "../../etc/passwd") is None


def test_load_index_surfaces_corrects_status(tmp_path):
    from hiveserve.resolver import load_index
    (tmp_path / "widgets").mkdir()
    (tmp_path / "widgets" / "corrections").mkdir()
    (tmp_path / "widgets" / "c.md").write_text("---\ntitle: C\ntype: concept\n---\n\nbody\n")
    (tmp_path / "widgets" / "corrections" / "fix.md").write_text(
        "---\ntitle: Fix\ntype: correction\ncorrects: widgets/c\nstatus: approved\n---\n\n## Correction\n\nx\n")
    idx = {c["id"]: c for c in load_index(tmp_path)}
    assert idx["widgets/c"]["corrects"] is None
    assert idx["widgets/corrections/fix"]["type"] == "correction"
    assert idx["widgets/corrections/fix"]["corrects"] == "widgets/c"
    assert idx["widgets/corrections/fix"]["status"] == "approved"


def test_corrections_by_target_active_only():
    from hiveserve.resolver import corrections_by_target
    index = [
        {"id": "widgets/c", "type": "concept"},
        {"id": "widgets/corrections/a", "type": "correction", "corrects": "widgets/c", "status": "approved"},
        {"id": "widgets/corrections/b", "type": "correction", "corrects": "widgets/c", "status": "superseded"},
    ]
    assert corrections_by_target(index) == {"widgets/c": ["widgets/corrections/a"]}


def test_resolve_copulls_active_correction(tmp_path):
    from hiveserve.resolver import resolve
    (tmp_path / "widgets").mkdir()
    (tmp_path / "widgets" / "corrections").mkdir()
    (tmp_path / "widgets" / "c.md").write_text("---\ntitle: C\ntype: concept\nrelated: []\n---\n\nconcept body\n")
    (tmp_path / "widgets" / "corrections" / "fix.md").write_text(
        "---\ntitle: Fix\ntype: correction\ncorrects: widgets/c\nstatus: approved\n---\n\n## Correction\n\nthe fix\n")
    res = resolve(tmp_path, ["widgets/c"])
    assert "widgets/corrections/fix" in res["card_ids"]
    assert "the fix" in res["bundle"]
    assert res["corrections"] == ["widgets/corrections/fix"]


def test_resolve_ignores_superseded_correction(tmp_path):
    from hiveserve.resolver import resolve
    (tmp_path / "widgets").mkdir()
    (tmp_path / "widgets" / "corrections").mkdir()
    (tmp_path / "widgets" / "c.md").write_text("---\ntitle: C\ntype: concept\nrelated: []\n---\n\nbody\n")
    (tmp_path / "widgets" / "corrections" / "old.md").write_text(
        "---\ntitle: Old\ntype: correction\ncorrects: widgets/c\nstatus: superseded\n---\n\n## Correction\n\nold\n")
    res = resolve(tmp_path, ["widgets/c"])
    assert res["corrections"] == []
    assert "old" not in res["bundle"].split("concept", 1)[-1] or "widgets/corrections/old" not in res["card_ids"]


def test_card_path_resolves_concept_and_client_trees(tmp_path):
    from hiveserve.resolver import card_path
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    (concepts / "widgets").mkdir(parents=True)
    (concepts / "widgets" / "a.md").write_text("---\ntitle: A\n---\n\nbody\n")
    (clients / "alpha" / "memory").mkdir(parents=True)
    (clients / "alpha" / "memory" / "m.md").write_text("---\ntitle: M\n---\n\nmem\n")
    assert card_path(concepts, "widgets/a", clients).name == "a.md"
    assert card_path(concepts, "clients/alpha/memory/m", clients).name == "m.md"
    assert card_path(concepts, "clients/alpha/memory/missing", clients) is None
    assert card_path(concepts, "../secret", clients) is None            # traversal blocked
    assert card_path(concepts, "clients/../../etc/passwd", clients) is None


def test_load_index_includes_client_memory(tmp_path):
    from hiveserve.resolver import load_index
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    (concepts / "widgets").mkdir(parents=True)
    (concepts / "widgets" / "a.md").write_text("---\ntitle: A\ndescription: d\nproduct: widgets\n---\n\nbody\n")
    (clients / "alpha" / "memory").mkdir(parents=True)
    (clients / "alpha" / "memory" / "m.md").write_text(
        "---\ntitle: Alpha Mem\ndescription: alpha note\ntype: memory\nclient: alpha\nproduct: widgets\n---\n\nmem\n")
    idx = {c["id"]: c for c in load_index(concepts, clients)}
    assert idx["widgets/a"]["client"] is None                       # concept rows carry client=None
    m = idx["clients/alpha/memory/m"]
    assert m["type"] == "memory" and m["client"] == "alpha" and m["product"] == "widgets"


def test_load_index_without_clients_dir_is_unchanged(tmp_path):
    from hiveserve.resolver import load_index
    (tmp_path / "x.md").write_text("---\ntitle: X\ndescription: d\n---\n\nbody\n")
    idx = load_index(tmp_path)                                  # no clients_dir
    assert [c["id"] for c in idx] == ["x"] and idx[0]["client"] is None


def test_load_index_skips_client_files_outside_memory_subfolder(tmp_path):
    from hiveserve.resolver import load_index
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    concepts.mkdir()
    (clients / "alpha" / "setup").mkdir(parents=True)
    (clients / "alpha" / "setup" / "notes.md").write_text("---\ntitle: N\n---\n\nx\n")   # not memory/
    idx = load_index(concepts, clients)
    assert idx == []                                            # only <client>/memory/<slug>.md counts


def _mk_client_world(tmp_path):
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    (concepts / "widgets").mkdir(parents=True)
    (concepts / "widgets" / "alloc.md").write_text(
        "---\ntitle: Alloc\ndescription: allocation\nproduct: widgets\nrelated: []\n---\n\nAlloc body.\n")
    (clients / "alpha" / "memory").mkdir(parents=True)
    (clients / "alpha" / "memory" / "alloc-mod.md").write_text(
        "---\ntitle: Alpha Alloc Mod\ndescription: alpha change\ntype: memory\nclient: alpha\n"
        "product: widgets\nrelated:\n- widgets/alloc\n---\n\nAlpha changed allocation.\n")
    (clients / "acme" / "memory").mkdir(parents=True)
    (clients / "acme" / "memory" / "a.md").write_text(
        "---\ntitle: ACME Mem\ndescription: acme\ntype: memory\nclient: acme\nproduct: widgets\nrelated: []\n---\n\nACME.\n")
    return concepts, clients


def test_resolve_client_memory_seed_only_in_scope(tmp_path):
    from hiveserve.resolver import resolve
    concepts, clients = _mk_client_world(tmp_path)
    mid = "clients/alpha/memory/alloc-mod"
    # in scope: alpha memory resolvable + pulls its related core concept
    out = resolve(concepts, [mid], depth=1, clients_dir=clients, client="alpha")
    assert mid in out["card_ids"] and "widgets/alloc" in out["card_ids"]
    # out of scope (no client): the memory seed is dropped, core stays pristine
    out2 = resolve(concepts, [mid], depth=1, clients_dir=clients, client=None)
    assert out2["card_ids"] == []
    # wrong client: alpha seed dropped under acme scope
    out3 = resolve(concepts, [mid], depth=1, clients_dir=clients, client="acme")
    assert out3["card_ids"] == []


def test_resolve_bfs_guards_cross_client_neighbour(tmp_path):
    from hiveserve.resolver import resolve
    concepts, clients = _mk_client_world(tmp_path)
    # a core concept that (pathologically) links to a alpha memory must not pull it when client!=alpha
    (concepts / "widgets" / "hub.md").write_text(
        "---\ntitle: Hub\ndescription: hub\nproduct: widgets\nrelated:\n- clients/alpha/memory/alloc-mod\n---\n\nHub.\n")
    out = resolve(concepts, ["widgets/hub"], depth=1, clients_dir=clients, client=None)
    assert out["card_ids"] == ["widgets/hub"]                      # alpha memory neighbour guarded out
    out2 = resolve(concepts, ["widgets/hub"], depth=1, clients_dir=clients, client="acme")
    assert out2["card_ids"] == ["widgets/hub"]                     # acme scope still can't reach alpha memory
    out3 = resolve(concepts, ["widgets/hub"], depth=1, clients_dir=clients, client="alpha")
    assert "clients/alpha/memory/alloc-mod" in out3["card_ids"]  # alpha scope reaches it


def test_resolve_concept_only_path_unchanged(tmp_path):
    from hiveserve.resolver import resolve
    (tmp_path / "a.md").write_text("---\ntitle: A\nrelated:\n- b\n---\n\nA.\n")
    (tmp_path / "b.md").write_text("---\ntitle: B\nrelated: []\n---\n\nB.\n")
    out = resolve(tmp_path, ["a"], depth=1)                    # no clients_dir/client
    assert out["card_ids"] == ["a", "b"]


def test_get_card_reads_client_tree(tmp_path):
    from hiveserve.resolver import get_card
    concepts, clients = _mk_client_world(tmp_path)
    assert "Alpha changed allocation." in get_card(concepts, "clients/alpha/memory/alloc-mod", clients)
    assert get_card(concepts, "clients/alpha/memory/nope", clients) is None


def test_resolve_scope_from_id_not_frontmatter(tmp_path):
    from hiveserve.resolver import resolve
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    (concepts / "widgets").mkdir(parents=True)
    (concepts / "widgets" / "a.md").write_text(
        "---\ntitle: A\nclient: alpha\nrelated: []\n---\n\nA body.\n")
    (clients / "alpha" / "memory").mkdir(parents=True)
    (clients / "alpha" / "memory" / "m.md").write_text(
        "---\ntitle: M\ntype: memory\nrelated: []\n---\n\nM body.\n")
    assert resolve(concepts, ["widgets/a"], clients_dir=clients, client=None)["card_ids"] == ["widgets/a"]
    mid = "clients/alpha/memory/m"
    assert resolve(concepts, [mid], clients_dir=clients, client=None)["card_ids"] == []
    assert mid in resolve(concepts, [mid], clients_dir=clients, client="alpha")["card_ids"]


def test_load_index_forces_memory_type_in_client_tree(tmp_path):
    from hiveserve.resolver import load_index
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    concepts.mkdir()
    (clients / "alpha" / "memory").mkdir(parents=True)
    (clients / "alpha" / "memory" / "x.md").write_text(
        "---\ntitle: X\ntype: correction\ncorrects: widgets/a\nclient: alpha\n---\n\nx\n")
    idx = {c["id"]: c for c in load_index(concepts, clients)}
    assert idx["clients/alpha/memory/x"]["type"] == "memory"


def test_load_index_excludes_db_tier(tmp_path):
    from hiveserve.resolver import get_card, load_index
    (tmp_path / "widgets").mkdir()
    (tmp_path / "widgets" / "replenishment.md").write_text(
        "---\ntitle: Replen\ndescription: d\nproduct: widgets\n---\nbody\n")
    dbdir = tmp_path / "widgets" / "db" / "tables"; dbdir.mkdir(parents=True)
    (dbdir / "T.md").write_text(
        "---\ntype: dbobject\nkind: table\ntitle: T\ndescription: d\nproduct: widgets\n---\nbody\n")
    ids = {c["id"] for c in load_index(tmp_path)}
    assert "widgets/replenishment" in ids
    assert "widgets/db/tables/T" not in ids                     # excluded from the concept index
    assert get_card(tmp_path, "widgets/db/tables/T") is not None  # but fetchable by id


# --------------------------------------------------------------------------
# "Leave CLIENTS_DIR empty to disable client memory" is what the docs and the
# shipped .env.example promise. Only `None` used to mean that: an empty string
# is not None, and Path("") is Path("."), which exists - so an unset setting
# scanned the working directory for <name>/memory/*.md and answered
# `clients/...` ids out of it.
# --------------------------------------------------------------------------

CLIENT_DECOY = "---\ntitle: Alpha Secret\ndescription: not ours\n---\n\nleaked body.\n"


def _corpus_with_a_client_shaped_decoy_in_the_working_dir(tmp_path, monkeypatch):
    concepts = tmp_path / "concepts"
    concepts.mkdir()
    (concepts / "alpha.md").write_text(CARD_A)
    decoy = tmp_path / "acme" / "memory"
    decoy.mkdir(parents=True)
    (decoy / "secret.md").write_text(CLIENT_DECOY)
    monkeypatch.chdir(tmp_path)
    return concepts


def test_an_empty_clients_dir_disables_client_memory_in_the_index(tmp_path, monkeypatch):
    concepts = _corpus_with_a_client_shaped_decoy_in_the_working_dir(tmp_path, monkeypatch)

    assert [c["id"] for c in load_index(concepts, "")] == ["alpha"]


def test_an_empty_clients_dir_does_not_serve_cards_out_of_the_working_directory(tmp_path,
                                                                                monkeypatch):
    concepts = _corpus_with_a_client_shaped_decoy_in_the_working_dir(tmp_path, monkeypatch)

    assert get_card(concepts, "clients/acme/memory/secret", "") is None


def test_a_configured_clients_dir_still_resolves_client_memory(tmp_path, monkeypatch):
    concepts = _corpus_with_a_client_shaped_decoy_in_the_working_dir(tmp_path, monkeypatch)
    clients = tmp_path / "clients" / "acme" / "memory"
    clients.mkdir(parents=True)
    (clients / "note.md").write_text(CLIENT_DECOY)

    idx = load_index(concepts, tmp_path / "clients")
    assert "clients/acme/memory/note" in {c["id"] for c in idx}
    assert get_card(concepts, "clients/acme/memory/note", tmp_path / "clients") == CLIENT_DECOY

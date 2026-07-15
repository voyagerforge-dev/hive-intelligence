from okfserve import tools

CARD = """---
title: Wave Replen
description: how replen feeds waves
related: []
sources: [wms.md]
---
Body text.
"""


def _seed(tmp_path):
    (tmp_path / "wave-replen.md").write_text(CARD)
    return tmp_path


def test_list_concepts(tmp_path):
    d = _seed(tmp_path)
    idx = tools.list_concepts(d)
    assert idx == [{"id": "wave-replen", "title": "Wave Replen",
                    "description": "how replen feeds waves", "regime": None,
                    "type": "concept", "version": None, "product": None,
                    "client": None, "corrects": None, "status": None}]


def test_list_concepts_excludes_corrections(tmp_path):
    (tmp_path / "wave-replen.md").write_text(CARD)
    correction_dir = tmp_path / "corrections"
    correction_dir.mkdir()
    correction_dir.joinpath("wave-replen-fix.md").write_text("""---
title: Wave Replen Fix
description: correction to replen feeding
related: []
sources: [wms.md]
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
    (concepts / "wms").mkdir(parents=True)
    (concepts / "wms" / "a.md").write_text("---\ntitle: A\ndescription: d\nproduct: wms\n---\n\nbody\n")
    (clients / "alpha" / "memory").mkdir(parents=True)
    (clients / "alpha" / "memory" / "m.md").write_text(
        "---\ntitle: M\ndescription: d\ntype: memory\nclient: alpha\nproduct: wms\n---\n\nmem\n")
    return concepts, clients


def test_list_concepts_client_scoped(tmp_path):
    from okfserve import tools
    concepts, clients = _client_world(tmp_path)
    ids_none = {c["id"] for c in tools.list_concepts(concepts, clients, client=None)}
    assert ids_none == {"wms/a"}                                 # no client -> no memory
    ids_alpha = {c["id"] for c in tools.list_concepts(concepts, clients, client="alpha")}
    assert ids_alpha == {"wms/a", "clients/alpha/memory/m"}          # alpha sees its memory
    ids_acme = {c["id"] for c in tools.list_concepts(concepts, clients, client="acme")}
    assert ids_acme == {"wms/a"}                                 # acme never sees alpha memory


def test_get_card_text_client_tree(tmp_path):
    from okfserve import tools
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
product: wms
---
body
""")
    idx = tools.list_concepts(tmp_path)
    ids = [c["id"] for c in idx]
    assert "wave-replen" in ids
    assert "db/tables/T" not in ids
    assert "No card" not in tools.get_card_text(tmp_path, "db/tables/T")

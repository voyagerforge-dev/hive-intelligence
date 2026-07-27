# knowledge/okf/tooling/hive-gen/tests/test_facets.py
from hivegen.facets import read_facets, card_regime, stamp_facets, cross_facet_edges, derive_versions

CARD = "---\ntitle: A\ndescription: d\nrelated:\n- b\ntype: concept\n---\n\nBody.\n"


def test_read_facets_and_regime():
    assert read_facets(CARD)["title"] == "A"
    assert card_regime(CARD) is None
    assert card_regime(stamp_facets(CARD, {"regime": "ops"})) == "ops"


def test_stamp_is_idempotent_and_preserves_body():
    once = stamp_facets(CARD, {"regime": "ops", "product": "wms"})
    twice = stamp_facets(once, {"regime": "ops", "product": "wms"})
    assert once == twice                      # idempotent
    assert once.count("regime:") == 1
    assert once.endswith("Body.\n")           # body untouched
    assert "type: concept" in once            # existing keys untouched


def test_stamp_does_not_overwrite_existing_key():
    stamped = stamp_facets(stamp_facets(CARD, {"regime": "ops"}), {"regime": "traditional"})
    assert card_regime(stamped) == "ops"      # first write wins; no duplicate


def test_cross_facet_edges_flags_crossing():
    a = stamp_facets("---\ntitle: A\nrelated:\n- b\n---\nx\n", {"regime": "ops"})
    b = stamp_facets("---\ntitle: B\nrelated: []\n---\ny\n", {"regime": "traditional"})
    c = stamp_facets("---\ntitle: C\nrelated:\n- b\n---\nz\n", {"regime": "traditional"})
    edges = cross_facet_edges({"a": a, "b": b, "c": c}, facet="regime")
    assert ("a", "b") in edges                # ops -> traditional crosses
    assert ("c", "b") not in edges            # traditional -> traditional is fine



_GUIDE = ("---\ntitle: X\nsources:\n"
          "- kind: wms-doc\n  ref: wms-wmos-warehouse-management-for-open-systems-2020-x-guide.md\n"
          "- kind: wms-doc\n  ref: wms-wmos-warehouse-management-for-open-systems-2018-x-guide.md\n"
          "---\nbody\n")
_FS = ("---\ntitle: Y\nsources:\n"
       "- kind: wms-doc\n  ref: wms-wmos-functional-specification-50000-outbound-distribution-y-fs.md\n"
       "---\nbody\n")


def test_derive_versions_sorted_unique():
    assert derive_versions(_GUIDE) == ["2018", "2020"]


def test_derive_versions_empty_for_fs_only():
    assert derive_versions(_FS) == []

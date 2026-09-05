import json

from hiveserve.dbobjects import search


def _seed(tmp_path):
    d = tmp_path / "widgets" / "db"
    d.mkdir(parents=True)
    rows = [
        {"id": "widgets/db/tables/ALLOCATION", "kind": "table", "module": "WM", "product": "widgets",
         "title": "ALLOCATION, order allocation records",
         "description": "Holds allocation of inventory to orders", "tags": ["table", "WM"]},
        {"id": "widgets/db/tables/MASTER_STAGING_DATA", "kind": "table", "module": "DOM", "product": "widgets",
         "title": "MASTER_STAGING_DATA", "description": "Stage inbound inventory events",
         "tags": ["table", "DOM"]},
        {"id": "widgets/db/plsql/DOM_ALLOC", "kind": "package", "module": "DOM", "product": "widgets",
         "title": "DOM_ALLOC", "description": "Allocation package", "tags": ["plsql", "DOM"]},
    ]
    (d / "manifest.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_search_by_comment_keyword_and_filters(tmp_path):
    _seed(tmp_path)
    hits = search(tmp_path, "allocation")
    ids = [h["id"] for h in hits]
    assert "widgets/db/tables/ALLOCATION" in ids and "widgets/db/plsql/DOM_ALLOC" in ids
    assert "widgets/db/tables/MASTER_STAGING_DATA" not in ids     # no 'allocation' match
    assert [h["id"] for h in search(tmp_path, "allocation", kind="table")] == ["widgets/db/tables/ALLOCATION"]
    assert search(tmp_path, "inbound", module="DOM")[0]["id"] == "widgets/db/tables/MASTER_STAGING_DATA"
    assert len(search(tmp_path, "a", limit=1)) == 1


def test_missing_manifest_returns_empty(tmp_path):
    assert search(tmp_path, "allocation") == []


def test_projected_fields_only(tmp_path):
    _seed(tmp_path)
    hit = search(tmp_path, "allocation")[0]
    assert set(hit.keys()) == {"id", "kind", "module", "product", "title", "description"}


def test_ranking_more_tokens_matched_first(tmp_path):
    _seed(tmp_path)
    hits = search(tmp_path, "allocation order inventory")
    ids = [h["id"] for h in hits]
    # ALLOCATION table matches all three tokens; DOM_ALLOC only matches 'allocation'
    assert ids[0] == "widgets/db/tables/ALLOCATION"


def test_search_matches_a_fragment_of_an_object_name(tmp_path):
    """A half-remembered name is how an agent reaches a schema object.

    Object names are identifiers, not English words, so this door matches substrings:
    `alloc` has to reach `ALLOCATION` and `stag` has to reach `MASTER_STAGING_DATA`.
    Whole-token matching, which `find_concepts` uses, would return neither.
    """
    _seed(tmp_path)
    assert "widgets/db/tables/ALLOCATION" in [h["id"] for h in search(tmp_path, "alloc")]
    assert [h["id"] for h in search(tmp_path, "stag")] == ["widgets/db/tables/MASTER_STAGING_DATA"]

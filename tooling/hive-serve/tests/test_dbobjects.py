import json

from hiveserve.dbobjects import search


def _seed(tmp_path):
    d = tmp_path / "wms" / "db"
    d.mkdir(parents=True)
    rows = [
        {"id": "wms/db/tables/ALLOCATION", "kind": "table", "module": "WM", "product": "wms",
         "title": "ALLOCATION, order allocation records",
         "description": "Holds allocation of inventory to orders", "tags": ["table", "WM"]},
        {"id": "wms/db/tables/MASTER_STAGING_DATA", "kind": "table", "module": "DOM", "product": "wms",
         "title": "MASTER_STAGING_DATA", "description": "Stage inbound inventory events",
         "tags": ["table", "DOM"]},
        {"id": "wms/db/plsql/DOM_ALLOC", "kind": "package", "module": "DOM", "product": "wms",
         "title": "DOM_ALLOC", "description": "Allocation package", "tags": ["plsql", "DOM"]},
    ]
    (d / "manifest.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_search_by_comment_keyword_and_filters(tmp_path):
    _seed(tmp_path)
    hits = search(tmp_path, "allocation")
    ids = [h["id"] for h in hits]
    assert "wms/db/tables/ALLOCATION" in ids and "wms/db/plsql/DOM_ALLOC" in ids
    assert "wms/db/tables/MASTER_STAGING_DATA" not in ids     # no 'allocation' match
    assert [h["id"] for h in search(tmp_path, "allocation", kind="table")] == ["wms/db/tables/ALLOCATION"]
    assert search(tmp_path, "inbound", module="DOM")[0]["id"] == "wms/db/tables/MASTER_STAGING_DATA"
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
    assert ids[0] == "wms/db/tables/ALLOCATION"

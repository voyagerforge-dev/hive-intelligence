from okfprep.slugs import slugify, doc_slug, assign_slugs


def test_slugify():
    assert slugify("WMS", "ASNs - Initiate ASN FS.docx") == "wms-asns-initiate-asn-fs"


def test_doc_slug_is_folder_qualified():
    # same filename in different folders → distinct slugs (no cross-folder overwrite)
    a = doc_slug("WMS", "wmos/a/Overview.docx")
    b = doc_slug("WMS", "wmos/b/Overview.docx")
    assert a != b and a == "wms-wmos-a-overview" and b == "wms-wmos-b-overview"
    # extension is dropped → same-folder .doc/.docx collapse to one slug (handled by format-dedup)
    assert doc_slug("WMS", "wmos/a/Overview.doc") == doc_slug("WMS", "wmos/a/Overview.docx")
    # root-level file matches the old basename slug (back-compat for un-foldered paths)
    assert doc_slug("WMS", "Dashboards.pdf") == "wms-dashboards"


def test_assign_slugs_de_collides_separator_variants():
    # 'Work Order.pdf' and 'Work_Order.pdf' both kebab to the same base → 2nd gets a -2 suffix
    inc = [
        {"path": "w/Work Order.pdf", "product": "WMS"},
        {"path": "w/Work_Order.pdf", "product": "WMS"},
        {"path": "w/Other.pdf", "product": "WMS"},
    ]
    slugs = assign_slugs(inc)
    assert slugs[0] == "wms-w-work-order"
    assert slugs[1] == "wms-w-work-order-2"   # distinct → no overwrite
    assert slugs[2] == "wms-w-other"
    assert len(set(slugs)) == 3

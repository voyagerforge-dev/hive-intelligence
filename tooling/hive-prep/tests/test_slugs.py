from hiveprep.slugs import assign_slugs, doc_slug, slugify


def test_slugify():
    assert slugify("WIDGETS", "ASNs - Initiate ASN FS.docx") == "widgets-asns-initiate-asn-fs"


def test_doc_slug_is_folder_qualified():
    # same filename in different folders → distinct slugs (no cross-folder overwrite)
    a = doc_slug("WIDGETS", "bench/a/Overview.docx")
    b = doc_slug("WIDGETS", "bench/b/Overview.docx")
    assert a != b and a == "widgets-bench-a-overview" and b == "widgets-bench-b-overview"
    # extension is dropped → same-folder .doc/.docx collapse to one slug (handled by format-dedup)
    assert doc_slug("WIDGETS", "bench/a/Overview.doc") == doc_slug("WIDGETS", "bench/a/Overview.docx")
    # root-level file matches the old basename slug (back-compat for un-foldered paths)
    assert doc_slug("WIDGETS", "Dashboards.pdf") == "widgets-dashboards"


def test_assign_slugs_de_collides_separator_variants():
    # 'Work Order.pdf' and 'Work_Order.pdf' both kebab to the same base → 2nd gets a -2 suffix
    inc = [
        {"path": "w/Work Order.pdf", "product": "WIDGETS"},
        {"path": "w/Work_Order.pdf", "product": "WIDGETS"},
        {"path": "w/Other.pdf", "product": "WIDGETS"},
    ]
    slugs = assign_slugs(inc)
    assert slugs[0] == "widgets-w-work-order"
    assert slugs[1] == "widgets-w-work-order-2"   # distinct → no overwrite
    assert slugs[2] == "widgets-w-other"
    assert len(set(slugs)) == 3

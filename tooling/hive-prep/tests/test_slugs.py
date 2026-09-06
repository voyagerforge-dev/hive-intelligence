import pytest

from hiveprep.slugs import assign_slugs, doc_slug, entry_product, slugify


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


# --- a missing product is a refusal, not a default ------------------------------------
# It used to fall back to the literal "WMS", the domain Hive was first built for. The
# product is the first segment of every slug, so that default silently filed a document
# under a product the corpus may not even have.

def test_a_product_less_include_is_refused_by_name(monkeypatch):
    monkeypatch.setattr("hiveprep.profile.load_curation_vocabulary",
                        lambda *a, **k: {"products": ["WIDGETS"], "platforms": []})
    with pytest.raises(ValueError) as e:
        entry_product({"path": "w/Work Order.pdf"})
    assert "w/Work Order.pdf" in str(e.value) and "product" in str(e.value)
    assert "WMS" not in str(e.value)     # the old default, gone rather than quietly used


def test_the_refusal_names_the_products_the_profile_declares(monkeypatch):
    """An operator can only fix this if they are told what the corpus accepts."""
    monkeypatch.setattr("hiveprep.profile.load_curation_vocabulary",
                        lambda *a, **k: {"products": ["GADGETS", "WIDGETS"], "platforms": []})
    with pytest.raises(ValueError, match="GADGETS, WIDGETS"):
        entry_product({"path": "w/Work Order.pdf"})


def test_the_refusal_says_so_when_the_profile_declares_none(monkeypatch):
    """Silence about the vocabulary would read as "there are none you may use"."""
    monkeypatch.setattr("hiveprep.profile.load_curation_vocabulary",
                        lambda *a, **k: {"products": [], "platforms": []})
    with pytest.raises(ValueError, match="declares no `curation.products`"):
        entry_product({"path": "w/Work Order.pdf"})


def test_an_empty_product_is_refused_like_a_missing_one():
    """`product: ""` in a plan is a filled-in field that says nothing."""
    for blank in ("", "   ", None):
        with pytest.raises(ValueError):
            entry_product({"path": "w/a.pdf", "product": blank})


def test_assign_slugs_refuses_rather_than_slugging_under_a_guess():
    with pytest.raises(ValueError):
        assign_slugs([{"path": "w/a.pdf", "product": "WIDGETS"}, {"path": "w/b.pdf"}])

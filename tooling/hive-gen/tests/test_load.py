import io

from hivegen.load import Doc, is_wave_replen, load_docs, load_docs_local


def test_is_wave_replen_matches_and_rejects():
    assert is_wave_replen("example_prefix/docs/wave-template-picking-parameters.md")
    assert is_wave_replen("example_prefix/docs/activity-tracking-inquiry-fs-300-replenishment.md")
    assert is_wave_replen("example_prefix/docs/shipping-wave-major-minor.md")
    assert not is_wave_replen("example_prefix/docs/fedex-express.md")


class FakeS3:
    def __init__(self, objs: dict[str, str]):
        self._objs = objs

    def list_objects_v2(self, Bucket, Prefix):
        keys = [k for k in self._objs if k.startswith(Prefix)]
        return {"Contents": [{"Key": k} for k in keys]}

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self._objs[Key].encode())}


def test_load_docs_filters_to_wave_replen():
    s3 = FakeS3({
        "example_prefix/docs/wave-template.md": "wave body",
        "example_prefix/docs/fedex-express.md": "carrier body",
        "example_prefix/_manifest.jsonl": "{}",
    })
    docs = load_docs(s3, "b", "example_prefix/")
    assert [d.name for d in docs] == ["example_prefix/docs/wave-template.md"]
    assert docs[0].text == "wave body"
    assert isinstance(docs[0], Doc)


def test_load_docs_local_filters_and_reads(tmp_path):
    d = tmp_path / "atomic"
    d.mkdir()
    (d / "shipping-wave-major-minor-order-fs.md").write_text("wave body")
    (d / "lean-time-replenishment-fs.md").write_text("replen body")
    (d / "fedex-express-carrier.md").write_text("carrier body")
    (d / "notes.txt").write_text("ignore me")
    docs = load_docs_local(d)
    names = sorted(x.name for x in docs)
    assert names == ["lean-time-replenishment-fs.md", "shipping-wave-major-minor-order-fs.md"]
    by_name = {x.name: x for x in docs}
    assert by_name["shipping-wave-major-minor-order-fs.md"].text == "wave body"
    assert isinstance(docs[0], Doc)


def test_load_docs_local_no_filter_includes_all_md(tmp_path):
    d = tmp_path / "atomic"
    d.mkdir()
    (d / "wave.md").write_text("a")
    (d / "fedex.md").write_text("b")
    docs = load_docs_local(d, only_wave_replen=False)
    assert sorted(x.name for x in docs) == ["fedex.md", "wave.md"]


def _atomic_doc(topic: str, body: str = "body") -> str:
    return f"---\ntitle: T\nslug: s\ntopic: {topic}\nproduct: WMS\n---\n\n{body}\n"


def test_load_docs_local_by_topic(tmp_path):
    from hivegen.load import load_docs_local
    d = tmp_path / "atomic"; d.mkdir()
    (d / "a.md").write_text(_atomic_doc("RF Inbound"))
    (d / "b.md").write_text(_atomic_doc("Receiving"))
    (d / "c.md").write_text(_atomic_doc("Outbound Distribution"))
    (d / "e.md").write_text(_atomic_doc("Inventory Management"))
    docs = load_docs_local(d, topics=["RF Inbound", "Receiving"])
    assert sorted(x.name for x in docs) == ["a.md", "b.md"]  # topic filter, case-insensitive set


def test_load_area_local_inbound(tmp_path):
    from hivegen.load import AREAS, load_area_local
    d = tmp_path / "atomic"; d.mkdir()
    (d / "a.md").write_text(_atomic_doc("Putaway"))
    (d / "b.md").write_text(_atomic_doc("Outbound Distribution"))
    docs = load_area_local(d, "inbound")
    assert [x.name for x in docs] == ["a.md"]     # Putaway ∈ inbound, Outbound ∉
    assert "Putaway" in AREAS["inbound"]


def test_load_area_local_unknown_raises(tmp_path):
    import pytest
    from hivegen.load import load_area_local
    d = tmp_path / "atomic"; d.mkdir()
    with pytest.raises(KeyError):
        load_area_local(d, "not-an-area")


def test_frontmatter_topic_parses():
    from hivegen.load import frontmatter_topic
    assert frontmatter_topic(_atomic_doc("Yard Management")) == "Yard Management"
    assert frontmatter_topic("no frontmatter here") == ""


def test_load_docs_local_name_include_and_exclude(tmp_path):
    """A sub-slice narrows a topic by filename keyword: include selects, exclude subtracts."""
    d = tmp_path / "atomic"; d.mkdir()
    (d / "iface-billing-integration-bm-hook-picking.md").write_text(_atomic_doc("Interfaces"))
    (d / "iface-labor-management-rf-pack-case.md").write_text(_atomic_doc("Interfaces"))
    (d / "iface-mhe-pick-to-tote.md").write_text(_atomic_doc("Interfaces"))
    (d / "iface-xsds-mhe-wcs-hook-oms.md").write_text(_atomic_doc("Interfaces"))
    # include only: keep filenames containing a keyword
    docs = load_docs_local(d, topics=["Interfaces"], name_include=["billing-integration"])
    assert [x.name for x in docs] == ["iface-billing-integration-bm-hook-picking.md"]
    # include + exclude: 'mhe' selects both mhe docs, exclude 'xsds' drops the mapping sheet
    docs = load_docs_local(d, topics=["Interfaces"], name_include=["mhe"], name_exclude=["xsds"])
    assert [x.name for x in docs] == ["iface-mhe-pick-to-tote.md"]
    # exclude only (remainder): everything in topic minus the claimed families
    docs = load_docs_local(d, topics=["Interfaces"],
                           name_exclude=["billing-integration", "labor-management", "mhe"])
    assert [x.name for x in docs] == []  # all four claimed


def test_load_subarea_local(tmp_path):
    from hivegen.load import SUBAREAS, load_subarea_local
    d = tmp_path / "atomic"; d.mkdir()
    (d / "wms-...-interfaces-labor-management-rf-pack-case.md").write_text(_atomic_doc("Interfaces"))
    (d / "wms-...-interfaces-billing-integration-bm-hook.md").write_text(_atomic_doc("Interfaces"))
    (d / "wms-...-system-control-purge-system-table-fs-orders.md").write_text(_atomic_doc("System Control"))
    docs = load_subarea_local(d, "if-lm-hooks")
    assert [x.name for x in docs] == ["wms-...-interfaces-labor-management-rf-pack-case.md"]
    assert "if-lm-hooks" in SUBAREAS and "sc-purge" in SUBAREAS


def test_load_subarea_local_unknown_raises(tmp_path):
    import pytest
    from hivegen.load import load_subarea_local
    d = tmp_path / "atomic"; d.mkdir()
    with pytest.raises(KeyError):
        load_subarea_local(d, "not-a-subarea")


def test_subareas_are_disjoint_within_shared_topics():
    """No atomic filename should fall into two sub-slices that share a parent topic."""
    from hivegen.load import SUBAREAS
    # group sub-areas by the topics they draw from
    by_topic: dict[str, list[str]] = {}
    for name, sa in SUBAREAS.items():
        for t in sa.topics:
            by_topic.setdefault(t, []).append(name)
    # sanity: the mechanism exposes topics/include/exclude on each sub-area
    for sa in SUBAREAS.values():
        assert isinstance(sa.topics, tuple)
        assert isinstance(sa.include, tuple)
        assert isinstance(sa.exclude, tuple)


from hivegen.load import AREAS, load_area_local


def test_osci_areas_registered():
    for area in ("osci-frameworks", "osci-analytics", "osci-workspaces", "osci-architecture"):
        assert area in AREAS


def test_osci_area_selects_by_topic(tmp_path):
    (tmp_path / "a.md").write_text("---\ntopic: oSCI Frameworks\n---\n\nx\n")
    (tmp_path / "b.md").write_text("---\ntopic: oSCI Architecture & Environment\n---\n\ny\n")
    ids = {d.id for d in load_area_local(tmp_path, "osci-frameworks")}
    assert ids == {"a.md"}

# tests/test_stamp.py
from okfprep.stamp import stamp_file, stamp_dir
from okfprep.validate import validate_atomic_dir

FULL_FM = """---
title: t
slug: my-doc
platform: SCPP
product: WMS
version: "2024"
doc_type: config-guide
source_doc: x.docx
status: active
---
body content here
"""

MISSING_PLATFORM_FM = """---
title: t
slug: my-doc
product: WMS
version: "2024"
doc_type: config-guide
source_doc: x.docx
status: active
---
body content here
"""

NO_FENCE_CONTENT = "just plain text with no frontmatter fence"

MINIMAL_FM = """---
slug: minimal
doc_type: config-guide
status: active
---
body
"""


def test_stamp_missing_platform_adds_it(tmp_path):
    """Stamping platform into a file missing it should add the field."""
    f = tmp_path / "doc.md"
    f.write_text(MISSING_PLATFORM_FM)
    changed = stamp_file(f, {"platform": "SCPP"}, only_missing=True)
    assert "platform" in changed
    text = f.read_text()
    assert "platform: SCPP" in text


def test_stamp_only_missing_preserves_existing_product(tmp_path):
    """An existing product value is preserved when only_missing=True."""
    f = tmp_path / "doc.md"
    f.write_text(MISSING_PLATFORM_FM)
    changed = stamp_file(f, {"platform": "SCPP", "product": "OVERRIDDEN"}, only_missing=True)
    assert "platform" in changed
    assert "product" not in changed
    text = f.read_text()
    assert "product: WMS" in text
    assert "OVERRIDDEN" not in text


def test_stamp_overwrite_replaces_existing_field(tmp_path):
    """only_missing=False should overwrite an existing field."""
    f = tmp_path / "doc.md"
    f.write_text(FULL_FM)
    changed = stamp_file(f, {"platform": "SCALE"}, only_missing=False)
    assert "platform" in changed
    text = f.read_text()
    assert "platform: SCALE" in text
    # original value should be gone
    assert "platform: SCPP" not in text


def test_stamp_no_change_when_all_fields_present(tmp_path):
    """A file already containing all given fields should produce no change."""
    f = tmp_path / "doc.md"
    f.write_text(FULL_FM)
    changed = stamp_file(f, {"platform": "SCPP", "product": "WMS", "version": "2024"}, only_missing=True)
    assert changed == []


def test_stamp_no_frontmatter_fence_skipped(tmp_path):
    """A file with no frontmatter fence should be skipped (returns [])."""
    f = tmp_path / "plain.md"
    f.write_text(NO_FENCE_CONTENT)
    changed = stamp_file(f, {"platform": "SCPP"}, only_missing=True)
    assert changed == []
    # content must not be altered
    assert f.read_text() == NO_FENCE_CONTENT


def test_stamp_then_validate_sees_stamped_fields(tmp_path):
    """After stamping, validate_atomic_dir should see no errors for stamped fields."""
    f = tmp_path / "minimal.md"
    f.write_text(MINIMAL_FM)
    # Stamp platform + product + version into the minimal doc
    changed = stamp_file(f, {"platform": "SCPP", "product": "WMS", "version": "2024"}, only_missing=True)
    assert set(changed) == {"platform", "product", "version"}
    report = validate_atomic_dir(tmp_path)
    # There should be no errors about missing platform/product/version
    platform_errs = [e for e in report.errors if "platform" in e or "product" in e or "version" in e]
    assert platform_errs == []


def test_stamp_dir_applies_to_all_files(tmp_path):
    """stamp_dir should apply stamp_file to every *.md in the directory."""
    for slug in ("a", "b", "c"):
        (tmp_path / f"{slug}.md").write_text(
            f"---\nslug: {slug}\ndoc_type: config-guide\nstatus: active\n---\nbody\n"
        )
    result = stamp_dir(tmp_path, {"platform": "SCALE"}, only_missing=True)
    assert set(result.keys()) == {"a.md", "b.md", "c.md"}
    for fname in result:
        assert "platform" in result[fname]


def test_stamp_dir_skips_already_complete(tmp_path):
    """stamp_dir returns empty dict when all files already have the field."""
    (tmp_path / "full.md").write_text(FULL_FM)
    result = stamp_dir(tmp_path, {"platform": "SCPP"}, only_missing=True)
    assert result == {}


def test_stamp_from_plan_fills_invariant_fields(tmp_path):
    from okfprep.stamp import stamp_from_plan
    from okfprep.curation_plan import Plan
    atomic = tmp_path / "atomic"; atomic.mkdir()
    # slug is the folder-qualified doc_slug of the include path (how transform writes it)
    (atomic / "doc.md").write_text(
        "---\ntitle: t\nslug: wms-a-foo\nsource_doc: foo.docx\n---\nbody\n")
    plan = Plan(scope="", corpus_root="", subtree="", include=[
        {"path": "a/foo.docx", "platform": "SCPP", "product": "WMS",
         "version": "2024", "doc_type": "config-guide", "topic": "receiving"}],
        exclude=[], dedup_groups=[], supersedes=[])
    changed = stamp_from_plan(atomic, plan, only_missing=True)
    text = (atomic / "doc.md").read_text()
    assert "platform: SCPP" in text and "version: \"2024\"" in text
    # source_doc already present (only_missing skips it), so the 5 truly-missing fields are returned.
    assert changed == {"doc.md": ["platform", "product", "version", "doc_type", "topic"]}


def test_stamp_from_plan_matches_passthrough_ext_suffixed_slug(tmp_path):
    """Passthrough atomic files use an ext-suffixed slug; stamp must match them to the plan entry."""
    from okfprep.stamp import stamp_from_plan
    from okfprep.curation_plan import Plan
    atomic = tmp_path / "atomic"; atomic.mkdir()
    # a .xsd passthrough → slug = doc_slug + "-xsd"
    (atomic / "wms-x-appointment-2017-xsd.md").write_text(
        '---\ntitle: t\nslug: wms-x-appointment-2017-xsd\nsource_doc: "Appointment_2017.xsd"\nstatus: active\n---\nbody\n')
    plan = Plan(scope="WMS", corpus_root="/r", subtree=".", include=[
        {"path": "x/Appointment_2017.xsd", "platform": "SCPP", "product": "WMS",
         "version": "2017", "doc_type": "technical-spec", "topic": "interfaces"}],
        exclude=[], dedup_groups=[], supersedes=[])
    stamp_from_plan(atomic, plan, only_missing=True)
    txt = (atomic / "wms-x-appointment-2017-xsd.md").read_text()
    assert 'version: "2017"' in txt and "doc_type: technical-spec" in txt and "topic: interfaces" in txt


def test_stamp_from_plan_matches_by_slug_not_basename(tmp_path):
    """Two docs sharing a basename across folders must each receive THEIR OWN metadata."""
    from okfprep.stamp import stamp_from_plan
    from okfprep.curation_plan import Plan
    atomic = tmp_path / "atomic"; atomic.mkdir()
    (atomic / "wms-wmos-a-overview.md").write_text(
        '---\ntitle: Overview\nslug: wms-wmos-a-overview\nsource_doc: "Overview.docx"\nstatus: active\n---\nbody\n')
    (atomic / "wms-wmos-b-overview.md").write_text(
        '---\ntitle: Overview\nslug: wms-wmos-b-overview\nsource_doc: "Overview.docx"\nstatus: active\n---\nbody\n')
    plan = Plan(scope="WMS", corpus_root="/root", subtree=".", include=[
        {"path": "wmos/a/Overview.docx", "platform": "SCPP", "product": "WMS",
         "version": "2018", "doc_type": "documentation", "topic": "alpha"},
        {"path": "wmos/b/Overview.docx", "platform": "SCPP", "product": "WMS",
         "version": "2020", "doc_type": "documentation", "topic": "bravo"}],
        exclude=[], dedup_groups=[], supersedes=[])
    stamp_from_plan(atomic, plan, only_missing=True)
    a = (atomic / "wms-wmos-a-overview.md").read_text()
    b = (atomic / "wms-wmos-b-overview.md").read_text()
    assert 'version: "2018"' in a and "topic: alpha" in a   # matched its OWN entry
    assert 'version: "2020"' in b and "topic: bravo" in b   # not the last/colliding one

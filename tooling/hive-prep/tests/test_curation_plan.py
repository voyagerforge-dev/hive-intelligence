import hiveprep.curation_plan as cp
from hiveprep.curation_plan import load_plan, validate_plan, dedup_format_variants, Plan


def test_dedup_format_variants_keeps_richest_and_records_drop():
    inc = [
        {"path": "bench/a/Spec FS.doc", "platform": "PLATFORM", "product": "WIDGETS", "doc_type": "functional-flow"},
        {"path": "bench/a/Spec FS.docx", "platform": "PLATFORM", "product": "WIDGETS", "doc_type": "functional-flow"},
        {"path": "bench/b/Other.pdf", "platform": "PLATFORM", "product": "WIDGETS", "doc_type": "documentation"},
        {"path": "bench/a/Overview.docx", "platform": "PLATFORM", "product": "WIDGETS", "doc_type": "documentation"},
        {"path": "bench/b/Overview.docx", "platform": "PLATFORM", "product": "WIDGETS", "doc_type": "documentation"},
    ]
    plan = Plan("WIDGETS", "/root", ".", inc, [], [], [])
    out = dedup_format_variants(plan)
    paths = {e["path"] for e in out.include}
    # .docx wins over .doc for the same folder+stem; the .doc is dropped
    assert "bench/a/Spec FS.docx" in paths and "bench/a/Spec FS.doc" not in paths
    # cross-folder same-stem (Overview in a/ vs b/) are NOT merged, both kept
    assert "bench/a/Overview.docx" in paths and "bench/b/Overview.docx" in paths
    assert "bench/b/Other.pdf" in paths
    assert len(out.include) == 4
    # the dropped variant is recorded as a dedup group
    dropped = [g for g in out.dedup_groups if "bench/a/Spec FS.doc" in g["drop"]]
    assert dropped and dropped[0]["keep"] == "bench/a/Spec FS.docx"


def test_dedup_format_variants_keeps_cross_family_distinct():
    """A .xsd schema beside a same-stem .xlsx mapping sheet are DIFFERENT artifacts, keep both."""
    inc = [
        {"path": "x/Foo.xlsx", "product": "WIDGETS"},
        {"path": "x/Foo.xls", "product": "WIDGETS"},   # same XLS family as .xlsx → dropped
        {"path": "x/Foo.xsd", "product": "WIDGETS"},   # different family → KEPT
        {"path": "x/Foo.vm", "product": "WIDGETS"},    # different family → KEPT
    ]
    out = dedup_format_variants(Plan("WIDGETS", "/r", ".", inc, [], [], []))
    paths = {e["path"] for e in out.include}
    assert "x/Foo.xlsx" in paths and "x/Foo.xls" not in paths   # XLS family deduped
    assert "x/Foo.xsd" in paths and "x/Foo.vm" in paths         # distinct families preserved

def _plan(tmp_path, body):
    (tmp_path/"a.pdf").write_bytes(b"x"); (tmp_path/"b.pdf").write_bytes(b"y")
    p = tmp_path/"plan.yaml"; p.write_text(body); return p

GOOD = """scope: WIDGETS
corpus_root: "{root}"
subtree: "."
include:
  - {{path: "a.pdf", platform: PLATFORM, product: WIDGETS, version: "2013", doc_type: technical-spec, topic: t, reason: r}}
exclude:
  - {{path: "b.pdf", reason: out of scope}}
dedup_groups: []
supersedes: []
"""

def test_valid_plan_no_errors(tmp_path):
    p = _plan(tmp_path, GOOD.format(root=tmp_path))
    plan = load_plan(p)
    assert validate_plan(plan, corpus_root=tmp_path) == []
    assert plan.include[0]["platform"] == "PLATFORM"

def test_missing_include_path_errors(tmp_path):
    body = GOOD.format(root=tmp_path).replace('path: "a.pdf"', 'path: "ghost.pdf"')
    assert any("ghost.pdf" in e for e in validate_plan(load_plan(_plan(tmp_path, body)), corpus_root=tmp_path))

def test_include_exclude_conflict_errors(tmp_path):
    body = GOOD.format(root=tmp_path).replace('path: "b.pdf", reason: out of scope', 'path: "a.pdf", reason: x')
    assert any("both include and exclude" in e for e in validate_plan(load_plan(_plan(tmp_path, body)), corpus_root=tmp_path))

def test_bad_enum_errors(tmp_path, monkeypatch):
    """The platform vocabulary is corpus-specific, so it is patched in rather than assumed."""
    monkeypatch.setattr(cp, "PLATFORMS", {"PLATFORM"})
    body = GOOD.format(root=tmp_path).replace("platform: PLATFORM", "platform: NOPE")
    assert any("platform" in e for e in validate_plan(load_plan(_plan(tmp_path, body)), corpus_root=tmp_path))


def test_enum_check_is_skipped_when_the_profile_declares_no_vocabulary(tmp_path, monkeypatch):
    """Empty means "not configured", not "reject everything". A plan validator that rejects
    every platform value would make hive-prep unusable against any other corpus."""
    monkeypatch.setattr(cp, "PLATFORMS", set())
    monkeypatch.setattr(cp, "PRODUCTS", set())
    body = GOOD.format(root=tmp_path).replace("platform: PLATFORM", "platform: ANYTHING")
    errors = validate_plan(load_plan(_plan(tmp_path, body)), corpus_root=tmp_path)
    assert not any("platform" in e for e in errors)

def test_dedup_keep_in_drop_errors(tmp_path):
    body = GOOD.format(root=tmp_path).replace("dedup_groups: []",
        'dedup_groups:\n  - {keep: "a.pdf", drop: ["a.pdf"], reason: r}')
    assert any("keep" in e and "drop" in e for e in validate_plan(load_plan(_plan(tmp_path, body)), corpus_root=tmp_path))


def test_dedup_drop_missing_errors(tmp_path):
    body = GOOD.format(root=tmp_path).replace("dedup_groups: []",
        'dedup_groups:\n  - {keep: "a.pdf", drop: ["ghost.pdf"], reason: r}')
    assert any("drop path missing" in e for e in validate_plan(load_plan(_plan(tmp_path, body)), corpus_root=tmp_path))

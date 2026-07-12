from okfprep.curation_plan import load_plan, validate_plan, dedup_format_variants, Plan


def test_dedup_format_variants_keeps_richest_and_records_drop():
    inc = [
        {"path": "wmos/a/Spec FS.doc", "platform": "SCPP", "product": "WMS", "doc_type": "functional-flow"},
        {"path": "wmos/a/Spec FS.docx", "platform": "SCPP", "product": "WMS", "doc_type": "functional-flow"},
        {"path": "wmos/b/Other.pdf", "platform": "SCPP", "product": "WMS", "doc_type": "documentation"},
        {"path": "wmos/a/Overview.docx", "platform": "SCPP", "product": "WMS", "doc_type": "documentation"},
        {"path": "wmos/b/Overview.docx", "platform": "SCPP", "product": "WMS", "doc_type": "documentation"},
    ]
    plan = Plan("WMS", "/root", ".", inc, [], [], [])
    out = dedup_format_variants(plan)
    paths = {e["path"] for e in out.include}
    # .docx wins over .doc for the same folder+stem; the .doc is dropped
    assert "wmos/a/Spec FS.docx" in paths and "wmos/a/Spec FS.doc" not in paths
    # cross-folder same-stem (Overview in a/ vs b/) are NOT merged — both kept
    assert "wmos/a/Overview.docx" in paths and "wmos/b/Overview.docx" in paths
    assert "wmos/b/Other.pdf" in paths
    assert len(out.include) == 4
    # the dropped variant is recorded as a dedup group
    dropped = [g for g in out.dedup_groups if "wmos/a/Spec FS.doc" in g["drop"]]
    assert dropped and dropped[0]["keep"] == "wmos/a/Spec FS.docx"


def test_dedup_format_variants_keeps_cross_family_distinct():
    """A .xsd schema beside a same-stem .xlsx mapping sheet are DIFFERENT artifacts — keep both."""
    inc = [
        {"path": "x/Foo.xlsx", "product": "WMS"},
        {"path": "x/Foo.xls", "product": "WMS"},   # same XLS family as .xlsx → dropped
        {"path": "x/Foo.xsd", "product": "WMS"},   # different family → KEPT
        {"path": "x/Foo.vm", "product": "WMS"},    # different family → KEPT
    ]
    out = dedup_format_variants(Plan("WMS", "/r", ".", inc, [], [], []))
    paths = {e["path"] for e in out.include}
    assert "x/Foo.xlsx" in paths and "x/Foo.xls" not in paths   # XLS family deduped
    assert "x/Foo.xsd" in paths and "x/Foo.vm" in paths         # distinct families preserved

def _plan(tmp_path, body):
    (tmp_path/"a.pdf").write_bytes(b"x"); (tmp_path/"b.pdf").write_bytes(b"y")
    p = tmp_path/"plan.yaml"; p.write_text(body); return p

GOOD = """scope: WMS
corpus_root: "{root}"
subtree: "."
include:
  - {{path: "a.pdf", platform: SCPP, product: WMS, version: "2013", doc_type: technical-spec, topic: t, reason: r}}
exclude:
  - {{path: "b.pdf", reason: out of scope}}
dedup_groups: []
supersedes: []
"""

def test_valid_plan_no_errors(tmp_path):
    p = _plan(tmp_path, GOOD.format(root=tmp_path))
    plan = load_plan(p)
    assert validate_plan(plan, corpus_root=tmp_path) == []
    assert plan.include[0]["platform"] == "SCPP"

def test_missing_include_path_errors(tmp_path):
    body = GOOD.format(root=tmp_path).replace('path: "a.pdf"', 'path: "ghost.pdf"')
    assert any("ghost.pdf" in e for e in validate_plan(load_plan(_plan(tmp_path, body)), corpus_root=tmp_path))

def test_include_exclude_conflict_errors(tmp_path):
    body = GOOD.format(root=tmp_path).replace('path: "b.pdf", reason: out of scope', 'path: "a.pdf", reason: x')
    assert any("both include and exclude" in e for e in validate_plan(load_plan(_plan(tmp_path, body)), corpus_root=tmp_path))

def test_bad_enum_errors(tmp_path):
    body = GOOD.format(root=tmp_path).replace("platform: SCPP", "platform: NOPE")
    assert any("platform" in e for e in validate_plan(load_plan(_plan(tmp_path, body)), corpus_root=tmp_path))

def test_dedup_keep_in_drop_errors(tmp_path):
    body = GOOD.format(root=tmp_path).replace("dedup_groups: []",
        'dedup_groups:\n  - {keep: "a.pdf", drop: ["a.pdf"], reason: r}')
    assert any("keep" in e and "drop" in e for e in validate_plan(load_plan(_plan(tmp_path, body)), corpus_root=tmp_path))


def test_dedup_drop_missing_errors(tmp_path):
    body = GOOD.format(root=tmp_path).replace("dedup_groups: []",
        'dedup_groups:\n  - {keep: "a.pdf", drop: ["ghost.pdf"], reason: r}')
    assert any("drop path missing" in e for e in validate_plan(load_plan(_plan(tmp_path, body)), corpus_root=tmp_path))

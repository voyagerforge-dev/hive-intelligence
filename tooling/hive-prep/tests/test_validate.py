# tests/test_validate.py
from pathlib import Path

from hiveprep.validate import validate_atomic_dir

FM = """---
title: "{t}"
slug: {s}
platform: PLATFORM
product: WIDGETS
version: "2024"
doc_type: config-guide
source_doc: "x.docx"
status: {st}
related: [{rel}]
{sup}
---
body
"""

def _write(d: Path, slug, related="", status="active", supersedes=None):
    sup = f"supersedes: {supersedes}" if supersedes else ""
    (d / f"{slug}.md").write_text(FM.format(t=slug, s=slug, st=status, rel=related, sup=sup))

def test_valid_corpus_builds_relations(tmp_path):
    _write(tmp_path, "a", related="b")
    _write(tmp_path, "b")
    report = validate_atomic_dir(tmp_path)
    assert report.errors == []
    types = {(e["from"], e["to"], e["type"]) for e in report.relations["edges"]}
    assert ("a", "b", "related") in types

def test_functional_flow_is_a_valid_doc_type(tmp_path):
    (tmp_path / "ff.md").write_text(
        '---\ntitle: t\nslug: ff\nplatform: PLATFORM\nproduct: WIDGETS\nversion: "2024"\n'
        'doc_type: functional-flow\nsource_doc: x.docx\nstatus: active\n---\nbody\n'
    )
    report = validate_atomic_dir(tmp_path)
    assert report.errors == []

def test_dangling_link_is_error(tmp_path):
    _write(tmp_path, "a", related="ghost")
    report = validate_atomic_dir(tmp_path)
    assert any("ghost" in e for e in report.errors)

def test_duplicate_slug_is_error(tmp_path):
    _write(tmp_path, "dup")
    (tmp_path / "dup2.md").write_text(FM.format(t="x", s="dup", st="active", rel="", sup=""))
    report = validate_atomic_dir(tmp_path)
    assert any("duplicate slug" in e.lower() for e in report.errors)

def test_bad_doc_type_is_error(tmp_path):
    (tmp_path / "x.md").write_text(FM.format(t="x", s="x", st="active", rel="", sup="").replace("config-guide", "nonsense-type"))
    report = validate_atomic_dir(tmp_path)
    assert any("doc_type" in e for e in report.errors)

def test_supersedes_cycle_is_error(tmp_path):
    _write(tmp_path, "a", supersedes="b")
    _write(tmp_path, "b", supersedes="a")
    report = validate_atomic_dir(tmp_path)
    assert any("cycle" in e.lower() for e in report.errors)

def test_missing_closing_fence_is_error(tmp_path):
    (tmp_path / "trunc.md").write_text("---\nslug: foo\nproduct: BENCH\n")
    report = validate_atomic_dir(tmp_path)
    assert any("fence" in e or "frontmatter" in e for e in report.errors)

def test_malformed_yaml_is_error(tmp_path):
    (tmp_path / "bad.md").write_text("---\ntitle: {unclosed\n---\nbody\n")
    report = validate_atomic_dir(tmp_path)
    assert any("YAML" in e or "yaml" in e for e in report.errors)

def test_missing_product_is_error(tmp_path):
    (tmp_path / "np.md").write_text('---\nslug: np\nplatform: PLATFORM\nversion: "2024"\ndoc_type: config-guide\nstatus: active\n---\nbody\n')
    report = validate_atomic_dir(tmp_path)
    assert any("product" in e for e in report.errors)

def test_scalar_related_does_not_char_iterate(tmp_path):
    # bare-string related pointing at an existing slug must resolve, not iterate chars
    (tmp_path / "a.md").write_text('---\nslug: a\nplatform: PLATFORM\nproduct: WIDGETS\nversion: "2024"\ndoc_type: config-guide\nstatus: active\nrelated: b\n---\nx\n')
    (tmp_path / "b.md").write_text('---\nslug: b\nplatform: PLATFORM\nproduct: WIDGETS\nversion: "2024"\ndoc_type: config-guide\nstatus: active\n---\ny\n')
    report = validate_atomic_dir(tmp_path)
    assert report.errors == []
    assert any(e["to"] == "b" and e["type"] == "related" for e in report.relations["edges"])

def test_missing_platform_is_error(tmp_path):
    (tmp_path / "np.md").write_text('---\nslug: np\nproduct: WIDGETS\nversion: "2024"\ndoc_type: config-guide\nstatus: active\n---\nbody\n')
    report = validate_atomic_dir(tmp_path)
    assert any("platform" in e for e in report.errors)

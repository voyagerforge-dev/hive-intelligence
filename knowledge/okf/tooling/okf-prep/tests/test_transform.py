from pathlib import Path

import okfprep.transform as tf
from okfprep.curation_plan import Plan


class FakeDocling:
    def __init__(self, md="# Doc\n\n| a | b |\n"): self.md = md; self.calls = 0
    def to_markdown(self, filename, content): self.calls += 1; return self.md


class FakeVision:
    def __init__(self): self.calls = 0
    def describe_image(self, png, prompt=""): self.calls += 1; return "*Figure: a screen*"


def test_route_tier_text_vs_vision():
    assert tf.route_tier(500, 0.9) == "text"          # text-rich wins regardless of images
    assert tf.route_tier(10, 0.9) == "vision"          # sparse + image-dominant → vision
    assert tf.route_tier(10, 0.1) == "text"            # sparse but not image-dominant → text


def test_passthrough_markdown(tmp_path):
    src = tmp_path / "labels.vm"
    src.write_text("#set($x = 1)")
    out = tf.passthrough_markdown(src)
    assert "```velocity" in out and "#set($x = 1)" in out


def test_extract_text_prefers_docling(tmp_path, monkeypatch):
    pdf = tmp_path / "d.pdf"; pdf.write_bytes(b"%PDF-1.4")
    dc = FakeDocling()
    out = tf.extract_text_markdown(pdf, docling=dc)
    assert dc.calls == 1 and "| a | b |" in out


def test_extract_text_falls_back_to_pymupdf_on_docling_error(tmp_path, monkeypatch):
    pdf = tmp_path / "d.pdf"; pdf.write_bytes(b"%PDF-1.4")

    class Boom:
        def to_markdown(self, *a, **k):
            from okfprep.docling_client import DoclingError
            raise DoclingError("down")

    monkeypatch.setattr(tf, "_pymupdf4llm_markdown", lambda p: "fallback md")
    out = tf.extract_text_markdown(pdf, docling=Boom())
    assert out == "fallback md"


def test_transform_pdf_text_tier_writes_atomic(tmp_path, monkeypatch):
    pdf = tmp_path / "s.pdf"; pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(tf, "pdf_text_profile", lambda p: {"pages": 3, "avg_chars": 800.0, "img_page_frac": 0.0})
    dc, vc = FakeDocling(), FakeVision()
    res = tf.transform_pdf(pdf, "s.pdf", "WMS", tmp_path / "atomic", docling=dc,
                           vision=vc, render_dir=tmp_path / "_pages")
    assert res.ok and res.tier == "text" and vc.calls == 0
    body = (tmp_path / "atomic" / f"{res.md_path.stem}.md").read_text()
    assert "extracted_via: text" in body


def test_transform_pdf_vision_tier_uses_qwen(tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"; pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(tf, "pdf_text_profile", lambda p: {"pages": 2, "avg_chars": 5.0, "img_page_frac": 0.9})
    def _fake_render(pdf, out):
        out.mkdir(parents=True, exist_ok=True)
        paths = [out / "p1.png", out / "p2.png"]
        for p in paths:
            p.write_bytes(b"x")
        return paths
    monkeypatch.setattr(tf, "render_pdf_pages", _fake_render)
    dc, vc = FakeDocling(), FakeVision()
    res = tf.transform_pdf(pdf, "scan.pdf", "WMS", tmp_path / "atomic", docling=dc,
                           vision=vc, render_dir=tmp_path / "_pages")
    assert res.ok and res.tier == "vision" and vc.calls == 2
    assert "extracted_via: vision" in (res.md_path).read_text()


def test_transform_plan_skips_path_less_include_without_crashing(tmp_path):
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()
    (corpus_root / "notes.txt").write_text("hello world")
    plan = Plan(
        scope="unit-test", corpus_root=str(corpus_root), subtree="",
        include=[
            {"product": "WMS"},                          # missing "path" — must not crash the batch
            {"path": "notes.txt", "product": "WMS"},      # valid passthrough entry
        ],
        exclude=[], dedup_groups=[], supersedes=[],
    )
    work_dir = tmp_path / "work"
    results = tf.transform_plan(plan, work_dir, docling=FakeDocling(), vision=FakeVision())
    assert len(results) == 2
    bad, good = results
    assert bad.ok is False and "missing" in bad.error
    assert good.ok is True and good.tier == "passthrough"


def test_transform_pdf_strips_boilerplate_when_enabled(tmp_path, monkeypatch):
    pdf = tmp_path / "s.pdf"; pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(tf, "pdf_text_profile",
                        lambda p: {"pages": 1, "avg_chars": 800.0, "img_page_frac": 0.0})
    md = ("# Replen\n\nCopyright 2013 Manhattan Associates. All Rights Reserved.\n"
          "Page 2 of 9\n\nWM triggers replenishment below minimum.\n")
    res = tf.transform_pdf(pdf, "s.pdf", "WMS", tmp_path / "atomic", docling=FakeDocling(md),
                           vision=FakeVision(), render_dir=tmp_path / "_pages",
                           strip_product="wmos")
    body = res.md_path.read_text()
    assert "Copyright" not in body and "Manhattan Associates" not in body
    assert "All Rights Reserved" not in body and "Page 2 of 9" not in body
    assert "WM triggers replenishment below minimum." in body   # content kept


def test_transform_pdf_keeps_boilerplate_when_disabled(tmp_path, monkeypatch):
    pdf = tmp_path / "s.pdf"; pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(tf, "pdf_text_profile",
                        lambda p: {"pages": 1, "avg_chars": 800.0, "img_page_frac": 0.0})
    md = "# Replen\n\nCopyright 2013 Manhattan Associates.\n\nReal content.\n"
    res = tf.transform_pdf(pdf, "s.pdf", "WMS", tmp_path / "atomic", docling=FakeDocling(md),
                           vision=FakeVision(), render_dir=tmp_path / "_pages",
                           strip_product=None)
    body = res.md_path.read_text()
    assert "Copyright 2013 Manhattan Associates." in body   # untouched when disabled

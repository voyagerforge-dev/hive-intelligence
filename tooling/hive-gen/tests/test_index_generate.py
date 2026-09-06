from hivegen.scripts import index_generate as mod


def test_index_excludes_corrections(tmp_path):
    (tmp_path / "widgets").mkdir(); (tmp_path / "widgets" / "corrections").mkdir()
    (tmp_path / "widgets" / "c.md").write_text("---\ntitle: C\ntype: concept\ndescription: d\n---\n\nb\n")
    (tmp_path / "widgets" / "corrections" / "fix.md").write_text(
        "---\ntitle: Fix\ntype: correction\ncorrects: widgets/c\nstatus: approved\n---\n\n## Correction\n\nx\n")
    mod.generate(str(tmp_path))
    prod_index = (tmp_path / "widgets" / "index.md").read_text()
    assert "/widgets/c.md" in prod_index
    assert "corrections/fix" not in prod_index

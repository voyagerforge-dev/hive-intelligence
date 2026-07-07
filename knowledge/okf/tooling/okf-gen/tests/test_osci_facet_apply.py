# knowledge/okf/tooling/okf-gen/tests/test_osci_facet_apply.py
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "osci_facet_apply",
    Path(__file__).resolve().parents[1] / "scripts" / "osci_facet_apply.py")
mod = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(mod)


def test_versions_for_card_unions_source_years(tmp_path):
    atomic = tmp_path / "atomic"; atomic.mkdir()
    (atomic / "s1.md").write_text("---\nversion: '2018'\n---\n\nx\n")
    (atomic / "s2.md").write_text("---\nversion: '2020'\n---\n\ny\n")
    card = ("---\ntitle: T\nsources:\n- kind: osci-doc\n  ref: s1.md\n"
            "- kind: osci-doc\n  ref: s2.md\n---\n\nbody\n")
    assert mod.versions_for_card(card, atomic) == ["2018", "2020"]


def test_apply_stamps_product_platform_version(tmp_path):
    atomic = tmp_path / "atomic"; atomic.mkdir()
    (atomic / "s1.md").write_text("---\nversion: '2020'\n---\n\nx\n")
    concepts = tmp_path / "concepts"; concepts.mkdir()
    (concepts / "card.md").write_text(
        "---\ntitle: T\nsources:\n- kind: osci-doc\n  ref: s1.md\n---\n\nbody\n")
    mod.apply(str(concepts), str(atomic))
    out = (concepts / "card.md").read_text()
    assert "product: osci" in out and "platform: open-systems" in out and "version:" in out

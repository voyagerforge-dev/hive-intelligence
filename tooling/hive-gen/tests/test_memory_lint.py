import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "memory_lint", Path(__file__).resolve().parents[1] / "scripts" / "memory_lint.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)
lint = mod.lint


def _concept(d, cid):
    p = d / f"{cid}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntitle: {cid}\ntype: concept\n---\n\nbody\n")


def _mem(d, client, slug, **fm):
    p = d / client / "memory" / f"{slug}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(f"{k}: {v}" for k, v in fm.items())
    p.write_text(f"---\ntype: memory\nclient: {client}\n{lines}\n---\n\n## Memory\n\nx\n")
    return f"clients/{client}/memory/{slug}"


def test_lint_clean(tmp_path):
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    _concept(concepts, "widgets/alloc")
    _mem(clients, "alpha", "m1", product="widgets", status="approved", related="[widgets/alloc]", tags="[a]")
    errors, candidates = lint(clients, concepts)
    assert errors == [] and candidates == []


def test_lint_dangling_related_and_bad_product(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "ALLOWED_PRODUCTS", {"widgets"})
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    concepts.mkdir()
    _mem(clients, "alpha", "m1", product="evil", status="approved",
         related="[widgets/missing]")
    errors, _ = lint(clients, concepts)
    assert any("product" in e for e in errors)
    assert any("widgets/missing" in e for e in errors)


def test_lint_skips_the_product_check_when_the_profile_declares_none(tmp_path, monkeypatch):
    """Empty means "not configured". Rejecting every product would make the linter
    unusable against any corpus whose vocabulary is not baked into the product."""
    monkeypatch.setattr(mod, "ALLOWED_PRODUCTS", set())
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    concepts.mkdir()
    _mem(clients, "alpha", "m1", product="anything", status="approved", related="[]")
    errors, _ = lint(clients, concepts)
    assert not any("product" in e for e in errors)


def test_lint_conflict_candidate_same_client_shared_related(tmp_path):
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    _concept(concepts, "widgets/alloc")
    a = _mem(clients, "alpha", "m1", product="widgets", status="approved", related="[widgets/alloc]")
    b = _mem(clients, "alpha", "m2", product="widgets", status="approved", related="[widgets/alloc]")
    _mem(clients, "acme", "m3", product="widgets", status="approved", related="[widgets/alloc]")  # other client
    _, candidates = lint(clients, concepts)
    assert {frozenset(c) for c in candidates} == {frozenset((a, b))}   # same client only

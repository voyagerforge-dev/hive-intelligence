"""Every published command refuses a corpus directory that is not there.

`Path("")` is `Path(".")`, and a glob over a directory that does not exist yields nothing
and raises nothing, so an unset shell variable reaching one of these commands produced a
confident zero-result instead of a failure: `0 errors`, an empty index, a card written into
a tree invented under the working directory, and from the conflict gate an authoritative
`state: success` over a memory change nothing scored. Publishing these as PATH commands is
what puts an unset variable in front of them, so the refusal is tested at the command.
"""
from __future__ import annotations

import pytest

from hivegen.scripts import (
    conformance_pass,
    correction_from_issue,
    corrections_lint,
    index_generate,
    memory_conflict_score,
    memory_from_issue,
    memory_lint,
    pr_conflict_gate,
)

HOLE = object()

# (command module, the positional the bad value goes in, argv with a hole for it)
CASES = [
    (conformance_pass, "concepts_dir", [HOLE]),
    (index_generate, "concepts_dir", [HOLE]),
    (corrections_lint, "concepts_dir", [HOLE]),
    (memory_lint, "clients_dir", [HOLE, "concepts"]),
    (memory_lint, "concepts_dir", ["clients", HOLE]),
    (memory_conflict_score, "clients_dir", [HOLE, "concepts"]),
    (memory_conflict_score, "concepts_dir", ["clients", HOLE]),
    (pr_conflict_gate, "clients_dir",
     [HOLE, "concepts", "--changed-file", "clients/acme/memory/note.md"]),
    (pr_conflict_gate, "concepts_dir",
     ["clients", HOLE, "--changed-file", "clients/acme/memory/note.md"]),
    (memory_from_issue, "clients_dir", ["body.md", HOLE]),
    (correction_from_issue, "concepts_dir", ["body.md", HOLE]),
]


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """A real tree, so the only thing wrong in each case is the one argument under test."""
    (tmp_path / "clients" / "acme" / "memory").mkdir(parents=True)
    (tmp_path / "concepts" / "widgets").mkdir(parents=True)
    (tmp_path / "concepts" / "widgets" / "alloc.md").write_text(
        "---\ntitle: A\ntype: concept\n---\n\nbody\n")
    (tmp_path / "body.md").write_text("### Title\n\nx\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize("bad", ["", "missing"], ids=["unset", "absent"])
@pytest.mark.parametrize(
    "module,setting,argv", CASES,
    ids=[f"{m.__name__.rsplit('.', 1)[-1]}-{s}" for m, s, _ in CASES])
def test_the_command_refuses_a_corpus_directory_that_is_not_there(
        module, setting, argv, bad, corpus):
    with pytest.raises(SystemExit) as exc:
        module.main([bad if a is HOLE else a for a in argv])
    assert setting in str(exc.value), (
        f"{module.__name__} refused without naming {setting}: {exc.value}")


def test_the_gate_names_the_directory_rather_than_the_gateway(corpus, monkeypatch):
    """Ordering matters: an absent clients tree is why no verdict is possible.

    Before this refusal existed the gate got as far as the gateway check, so the operator
    was told to configure a model when the real fault was a path that is not there - and
    with a gateway configured in CI it got past that too, scored an empty tree, and posted
    `state: success` over a memory change.
    """
    monkeypatch.setenv("BIFROST_BASE", "http://gateway.invalid/v1")
    monkeypatch.setenv("BIFROST_API_KEY", "k")
    with pytest.raises(SystemExit) as exc:
        pr_conflict_gate.main(["missing/clients", "concepts",
                               "--changed-file", "missing/clients/acme/memory/note.md"])
    assert "clients_dir" in str(exc.value)
    assert "BIFROST" not in str(exc.value)


def test_conformance_pass_refuses_before_rewriting_anything(tmp_path, monkeypatch):
    """The destructive case, and the reason this is a refusal rather than a warning.

    `hivegen-conformance-pass "$CONCEPTS"` with the variable unset used to reach
    `process("")`, whose recursive glob starts at the filesystem ROOT and rewrites every
    markdown file that splits into three `---` parts, in place.
    """
    canary = tmp_path / "notes.md"
    canary.write_text("---\ntitle: Mine\n---\n\nkeep this\n")
    before = canary.read_text()
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as exc:
        conformance_pass.main([""])

    assert "concepts_dir" in str(exc.value)
    assert canary.read_text() == before, "the pass rewrote a file outside any corpus"


def test_an_empty_but_present_corpus_tree_is_still_a_success(tmp_path, monkeypatch):
    """"Set, and a directory" - not "looks like a corpus".

    A corpus that has not been generated yet legitimately holds almost nothing, and a
    refusal that reads emptiness as misconfiguration replaces one wrong answer with
    another.
    """
    (tmp_path / "clients").mkdir()
    (tmp_path / "concepts").mkdir()
    monkeypatch.chdir(tmp_path)

    assert memory_lint.main(["clients", "concepts"]) == 0
    assert corrections_lint.main(["concepts"]) == 0
    assert conformance_pass.main(["concepts"]) == 0
    assert index_generate.main(["concepts"]) == 0
    assert (tmp_path / "concepts" / "index.md").is_file()

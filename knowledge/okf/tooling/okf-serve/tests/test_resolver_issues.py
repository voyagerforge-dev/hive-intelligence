from okfserve.resolver import load_index


def test_issue_cards_are_indexed_client_scoped(tmp_path):
    concepts = tmp_path / "concepts"
    concepts.mkdir()
    (concepts / "a.md").write_text("---\ntype: concept\ntitle: A\n---\n")

    issues = tmp_path / "clients" / "alpha" / "issues"
    issues.mkdir(parents=True)
    (issues / "14872-wave.md").write_text(
        "---\ntype: issue\ntitle: Wave stalls\nclient: alpha\nstatus: distilled\n---\n")

    memory = tmp_path / "clients" / "alpha" / "memory"
    memory.mkdir(parents=True)
    (memory / "m.md").write_text("---\ntype: memory\ntitle: M\n---\n")

    idx = load_index(concepts, tmp_path / "clients")
    by_id = {c["id"]: c for c in idx}

    issue = by_id["clients/alpha/issues/14872-wave"]
    assert issue["type"] == "issue"
    assert issue["client"] == "alpha"
    assert issue["title"] == "Wave stalls"
    assert issue["status"] == "distilled"
    assert by_id["clients/alpha/memory/m"]["type"] == "memory"


def test_other_client_subdirs_are_still_ignored(tmp_path):
    concepts = tmp_path / "concepts"
    concepts.mkdir()
    scratch = tmp_path / "clients" / "alpha" / "scratch"
    scratch.mkdir(parents=True)
    (scratch / "note.md").write_text("---\ntype: concept\ntitle: N\n---\n")

    idx = load_index(concepts, tmp_path / "clients")
    assert all("scratch" not in c["id"] for c in idx)


def _corpus(tmp_path):
    concepts = tmp_path / "concepts"
    concepts.mkdir()
    (concepts / "a.md").write_text("---\ntype: concept\ntitle: A\n---\n")
    issues = tmp_path / "clients" / "alpha" / "issues"
    issues.mkdir(parents=True)
    (issues / "14872-wave.md").write_text(
        "---\ntype: issue\ntitle: Wave stalls\nclient: alpha\n---\n")
    other = tmp_path / "clients" / "beta" / "issues"
    other.mkdir(parents=True)
    (other / "999-x.md").write_text("---\ntype: issue\ntitle: X\nclient: beta\n---\n")
    return concepts, tmp_path / "clients"


def test_issues_never_dilute_a_general_concept_listing(tmp_path):
    from okfserve.tools import list_concepts
    concepts, clients = _corpus(tmp_path)
    ids = {c["id"] for c in list_concepts(concepts, clients, client=None)}
    assert ids == {"a"}


def test_issues_surface_only_for_their_own_client(tmp_path):
    from okfserve.tools import list_concepts
    concepts, clients = _corpus(tmp_path)
    ids = {c["id"] for c in list_concepts(concepts, clients, client="alpha")}
    assert "clients/alpha/issues/14872-wave" in ids
    assert "clients/beta/issues/999-x" not in ids

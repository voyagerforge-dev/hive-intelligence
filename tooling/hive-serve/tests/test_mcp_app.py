import anyio

from hiveserve import ledger
from hiveserve.config import Settings
from hiveserve.mcp_app import build_mcp


def _factory(ledger_dsn):
    return lambda: ledger.session(ledger_dsn)


def test_tools_registered_and_no_prompts(tmp_path, ledger_dsn):
    s = Settings(concepts_dir=str(tmp_path))
    mcp = build_mcp(s, _factory(ledger_dsn))
    tool_names = {t.name for t in anyio.run(mcp.list_tools)}
    assert {"list_concepts", "get_card", "resolve", "find_db_objects", "start_objective",
            "append_entry", "set_status", "record_quiz_result",
            "list_objectives", "get_objective",
            "remember", "recall", "forget", "promote"} <= tool_names
    assert anyio.run(mcp.list_prompts) == []   # personas moved to the Cowork plugin skills


def test_tool_dispatch_increments_metric(tmp_path, ledger_dsn):
    # End-to-end: dispatching a tool through FastMCP's real call_tool path must run
    # the @track_tool wrapper (not just the standalone-decorator tests), so the
    # mcp_tool_calls_total counter moves for the dispatched tool name.
    from hiveserve import metrics
    s = Settings(concepts_dir=str(tmp_path), clients_dir=str(tmp_path))
    mcp = build_mcp(s, _factory(ledger_dsn))
    labels = {"tool": "list_concepts", "outcome": "ok"}
    before = metrics.REGISTRY.get_sample_value("mcp_tool_calls_total", labels) or 0.0
    anyio.run(lambda: mcp.call_tool("list_concepts", {}))
    after = metrics.REGISTRY.get_sample_value("mcp_tool_calls_total", labels) or 0.0
    assert after == before + 1


def test_owner_from_ctx_defaults_without_request(tmp_path, ledger_dsn):
    from hiveserve.mcp_app import owner_from_ctx

    class _Req:
        request = None

    class _Ctx:
        request_context = _Req()

    s = Settings()
    assert owner_from_ctx(_Ctx(), s) == s.okf_default_owner


def test_list_concepts_tool_client_scoped(tmp_path, ledger_dsn):
    from hiveserve import tools
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    (concepts / "widgets").mkdir(parents=True)
    (concepts / "widgets" / "a.md").write_text("---\ntitle: A\ndescription: d\n---\n\nbody\n")
    (clients / "alpha" / "memory").mkdir(parents=True)
    (clients / "alpha" / "memory" / "m.md").write_text(
        "---\ntitle: M\ndescription: d\ntype: memory\nclient: alpha\n---\n\nmem\n")
    # exercise the underlying tool wiring the MCP closure calls (closures need a request ctx to invoke)
    assert {c["id"] for c in tools.list_concepts(concepts, clients, client=None)} == {"widgets/a"}
    assert {c["id"] for c in tools.list_concepts(concepts, clients, client="alpha")} == {
        "widgets/a", "clients/alpha/memory/m"}


# --------------------------------------------------------------------------
# An unset CONCEPTS_DIR is Path(""), which is Path("."), which exists. The
# catalogue was therefore built out of whatever markdown sat in the process
# working directory - in an engine checkout, this repository's own docs -
# and served as OKF concept cards. Refuse at startup, like LEDGER_DSN does.
# --------------------------------------------------------------------------

import pytest


def _decoy_working_directory(tmp_path, monkeypatch):
    """A working directory holding markdown that would pass for a card."""
    (tmp_path / "AGENTS.md").write_text(
        "---\ntitle: Engine notes\ndescription: not a card\n---\n\nengine prose\n")
    monkeypatch.chdir(tmp_path)


def test_mcp_door_refuses_an_unset_concepts_dir_instead_of_serving_the_working_directory(
        tmp_path, monkeypatch):
    _decoy_working_directory(tmp_path, monkeypatch)

    with pytest.raises(SystemExit) as exc:
        build_mcp(Settings(concepts_dir=""), lambda: None)
    assert "CONCEPTS_DIR" in str(exc.value)


def test_mcp_door_refuses_a_concepts_dir_that_is_not_there(tmp_path, monkeypatch):
    _decoy_working_directory(tmp_path, monkeypatch)
    missing = tmp_path / "gone"

    with pytest.raises(SystemExit) as exc:
        build_mcp(Settings(concepts_dir=str(missing)), lambda: None)
    assert "CONCEPTS_DIR" in str(exc.value) and str(missing) in str(exc.value)


def test_rest_door_refuses_an_unset_concepts_dir(tmp_path, monkeypatch):
    from hiveserve.app import build_rest_router

    _decoy_working_directory(tmp_path, monkeypatch)

    with pytest.raises(SystemExit) as exc:
        build_rest_router(Settings(concepts_dir=""))
    assert "CONCEPTS_DIR" in str(exc.value)


def _two_client_world(tmp_path):
    """Concepts plus two clients, each with memory and issue history."""
    concepts = tmp_path / "concepts"
    clients = tmp_path / "clients"
    (concepts / "widgets").mkdir(parents=True)
    (concepts / "widgets" / "allocation-process.md").write_text(
        "---\ntitle: Allocation Process\ndescription: how allocation assigns inventory\n---\n\nbody\n")
    for name in ("alpha", "acme"):
        (clients / name / "memory").mkdir(parents=True)
        (clients / name / "memory" / "second-scan.md").write_text(
            f"---\ntitle: {name} second scan\ndescription: an extra allocation scan step\n"
            f"type: memory\n---\n\nmem\n")
        (clients / name / "issues").mkdir()
        (clients / name / "issues" / "allocation.md").write_text(
            "---\ntitle: Allocation incident\ndescription: allocation scan failed\n"
            "type: issue\n---\n\nincident\n")
    return concepts, clients


def test_find_concepts_tool_searches_only_selected_client_memory(tmp_path):
    """Dispatched through FastMCP's real call_tool path, not the underlying function.

    Client memory used to be unreachable through search at every door: `find_concepts`
    filtered to `type == "concept"` and accepted no client, so an agent that did not
    already know a memory card's id could not find it.
    """
    concepts, clients = _two_client_world(tmp_path)
    s = Settings(concepts_dir=str(concepts), clients_dir=str(clients))

    def no_ledger():
        raise AssertionError("Retrieval must not access the ledger")

    mcp = build_mcp(s, no_ledger)

    def search(**kwargs):
        _, structured = anyio.run(
            lambda: mcp.call_tool("find_concepts", {"query": "allocation scan", **kwargs}))
        return {h["id"] for h in structured["result"]}

    assert search(client="alpha") == {"widgets/allocation-process",
                                      "clients/alpha/memory/second-scan"}
    assert search() == {"widgets/allocation-process"}        # unnamed: unchanged
    assert search(client="acme") == {"widgets/allocation-process",
                                     "clients/acme/memory/second-scan"}  # never alpha's

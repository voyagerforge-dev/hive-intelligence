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

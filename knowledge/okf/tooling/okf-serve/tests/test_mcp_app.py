import anyio

from okfserve import ledger
from okfserve.config import Settings
from okfserve.mcp_app import build_mcp


def _factory(tmp_path):
    db = tmp_path / "obj.db"
    return lambda: ledger.session(db)


def test_tools_and_prompts_registered(tmp_path):
    s = Settings(concepts_dir=str(tmp_path))
    mcp = build_mcp(s, _factory(tmp_path))
    tool_names = {t.name for t in anyio.run(mcp.list_tools)}
    prompt_names = {p.name for p in anyio.run(mcp.list_prompts)}
    assert {"list_concepts", "get_card", "resolve", "start_objective",
            "append_entry", "set_status", "record_quiz_result",
            "list_objectives", "get_objective"} <= tool_names
    assert {"investigate", "implementation_advisor", "guided_learning"} <= prompt_names


def test_owner_from_ctx_defaults_without_request(tmp_path):
    from okfserve.mcp_app import owner_from_ctx

    class _Req:
        request = None

    class _Ctx:
        request_context = _Req()

    s = Settings()
    assert owner_from_ctx(_Ctx(), s) == s.okf_default_owner

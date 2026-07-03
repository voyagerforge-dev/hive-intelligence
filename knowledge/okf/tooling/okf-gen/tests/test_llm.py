from okfgen.llm import extract_json


def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    assert extract_json('```json\n{"a": 2}\n```') == {"a": 2}


def test_extract_json_garbage_returns_none():
    assert extract_json("not json") is None
    assert extract_json("") is None


def test_extract_json_strips_think_block():
    # reasoning models (minimax-m3) emit <think>…</think> before the answer;
    # the reasoning can mention braces, which must not derail extraction.
    raw = '<think>I should return {concepts}. Let me build {the} object.</think>\n{"a": 3}'
    assert extract_json(raw) == {"a": 3}


def test_extract_json_think_block_with_fenced_json():
    raw = '<think>planning {x}</think>\n```json\n{"a": 4}\n```'
    assert extract_json(raw) == {"a": 4}


def test_bifrost_retries_then_succeeds(monkeypatch):
    import httpx

    from okfgen import llm as llm_mod

    calls = {"n": 0}

    class FakeResp:
        status_code = 200

        def raise_for_status(self): ...

        def json(self):
            return {"choices": [{"message": {"content": "OK"}}]}

    def fake_post(url, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("boom")
        return FakeResp()

    monkeypatch.setattr(llm_mod.httpx, "post", fake_post)
    monkeypatch.setattr(llm_mod.time, "sleep", lambda *_: None)
    c = llm_mod.BifrostChat("http://bf/v1", "k", "m", retries=3)
    assert c.complete("s", "u") == "OK"
    assert calls["n"] == 3


def test_bifrost_returns_none_after_exhausting_retries(monkeypatch):
    import httpx

    from okfgen import llm as llm_mod

    def fake_post(url, **kw):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(llm_mod.httpx, "post", fake_post)
    monkeypatch.setattr(llm_mod.time, "sleep", lambda *_: None)
    c = llm_mod.BifrostChat("http://bf/v1", "k", "m", retries=2)
    assert c.complete("s", "u") is None

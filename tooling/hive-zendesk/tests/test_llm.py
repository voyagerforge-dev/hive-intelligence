from importlib import metadata

import httpx
import respx

from hivezendesk.llm import BifrostChat

BASE = "http://bifrost:8080"


@respx.mock
def test_complete_sends_bearer_and_installed_version():
    route = respx.post(f"{BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "done"}, "finish_reason": "stop"}]},
        )
    )
    client = BifrostChat(BASE, "k", "test-model", retries=1)

    assert client.complete("system prompt", "user prompt") == "done"
    req = route.calls[0].request
    assert req.headers["Authorization"] == "Bearer k"
    assert req.headers["User-Agent"] == (
        f"hivezendesk/{metadata.version('vf-hive-zendesk')}"
    )

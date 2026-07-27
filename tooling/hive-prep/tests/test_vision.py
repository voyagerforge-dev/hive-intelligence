import httpx
import respx

from hiveprep.vision import QwenVisionClient, strip_think

BASE = "http://qwen.test"


def _msg(content):
    return {"choices": [{"message": {"content": content}}]}


@respx.mock
def test_describe_image_returns_markdown():
    respx.post(f"{BASE}/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_msg("## Page\n\n*Figure: a config screen*")))
    c = QwenVisionClient(base=BASE, api_key="k", model="qwen3.6-27b", timeout_s=5)
    out = c.describe_image(b"\x89PNG...", "convert this page")
    assert "Figure:" in out


def test_strip_think_unwraps_reasoning():
    assert strip_think("<think>reasoning</think>real body") == "real body"
    assert strip_think("<answer>payload</answer>") == "payload"
    assert strip_think("plain") == "plain"

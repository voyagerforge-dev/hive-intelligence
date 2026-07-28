"""Qwen3.6-27B vision client (Host-D, OpenAI-compatible). Renders a document page image to
clean markdown; describes figures/diagrams that text extraction drops. Replaces the retired
GLM-4.1V tier, same OpenAI /v1/chat/completions image_url shape."""
from __future__ import annotations

import base64
import re

import httpx

PAGE_PROMPT = (
    "Convert THIS single page of a Manhattan WMS document to clean GitHub-flavored Markdown. "
    "Preserve tables as markdown tables; keep headings and lists. For any figure/diagram/screenshot, "
    "insert a concise factual description in italics, e.g. *Figure: <what is visibly shown>*. "
    "Output ONLY the markdown for this page, no preamble, no commentary."
)

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_ANSWER = re.compile(r"<answer>(.*?)</answer>", re.DOTALL)

# Qwen (reasoning) may spend completion budget inside <think> before the answer; clear it.
MAX_TOKENS = 16000


class VisionError(RuntimeError):
    pass


def strip_think(text: str) -> str:
    text = _THINK.sub("", text or "")
    if "<think>" in text and "</think>" not in text:
        text = text.split("<think>", 1)[0]
    text = text.strip()
    m = _ANSWER.search(text)
    if m:
        return m.group(1).strip()
    if "<answer>" in text:
        return text.split("<answer>", 1)[1].replace("</answer>", "").strip()
    return text


class QwenVisionClient:
    def __init__(self, *, base: str, api_key: str, model: str, timeout_s: int = 600):
        self._url = base.rstrip("/") + "/v1/chat/completions"
        self._key = api_key
        self._model = model
        self._timeout = timeout_s

    def describe_image(self, png: bytes, prompt: str = PAGE_PROMPT) -> str:
        b64 = base64.b64encode(png).decode()
        body = {
            "model": self._model, "max_tokens": MAX_TOKENS, "temperature": 0.0,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]}],
        }
        try:
            r = httpx.post(self._url, headers={"Authorization": f"Bearer {self._key}"},
                           json=body, timeout=self._timeout)
        except httpx.HTTPError as e:
            raise VisionError(f"qwen vision request failed: {e}") from e
        if r.status_code != 200:
            raise VisionError(f"qwen vision {r.status_code}: {r.text[:200]}")
        msg = r.json()["choices"][0]["message"]
        # vLLM with a reasoning parser puts thoughts in reasoning_content, leaving content clean;
        # strip_think is the belt-and-suspenders fallback for inline <think>/<answer>.
        return strip_think(msg.get("content") or "")

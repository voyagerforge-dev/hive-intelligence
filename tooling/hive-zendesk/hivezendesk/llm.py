"""Bifrost (OpenAI-compatible) chat client + defensive JSON extraction.

Vendored rather than imported: okf packages are standalone (see hive-dbparse).
"""
from __future__ import annotations

import json
import re
import time
from typing import Protocol

import httpx

from . import USER_AGENT


class ChatLLM(Protocol):
    def complete(self, system: str, user: str) -> str | None: ...


_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> dict | None:
    # Reasoning models wrap chain-of-thought in <think>...</think> before the answer;
    # that prose can contain braces, so strip it first.
    text = _THINK.sub("", text or "").strip()
    if not text:
        return None
    m = _FENCE.search(text)
    candidate = m.group(1) if m else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        data = json.loads(candidate[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


class BifrostChat:
    """Chat client for Bifrost.

    NB the on-prem Qwen (`qwen3.8-27b`; `qwen3.6-27b` before 2026-08-24) is a REASONING model: it emits
    `reasoning`/`reasoning_details` and only adds `content` once it has finished
    thinking. Two consequences, both learned the hard way against the live endpoint:

    * `message["content"]` raises KeyError when the model is still mid-thought, which
      a broad `except` turns into a silent "distillation failed" for every ticket.
      Content is therefore read defensively.
    * With too small a `max_tokens` the model spends the whole budget reasoning and
      returns no answer at all (`finish_reason: length`). The budget must cover
      thinking AND the answer. `chat_template_kwargs`/`extra_body` do NOT pass through
      Bifrost to vLLM, so thinking cannot be switched off client-side - headroom is
      the only lever.
    """

    def __init__(self, base: str, api_key: str, model: str, timeout_s: int = 300,
                 retries: int = 4, backoff_s: float = 2.0, max_tokens: int = 4000) -> None:
        self._url = base.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}",
                         "User-Agent": USER_AGENT}
        self._model = model
        self._timeout = timeout_s
        self._retries = max(1, retries)
        self._backoff = backoff_s
        self._max_tokens = max_tokens

    @property
    def model(self) -> str:
        return self._model

    def complete(self, system: str, user: str) -> str | None:
        # Callers treat None as a hard failure (skip the ticket), so a transient blip
        # must not silently look like a decision.
        for attempt in range(self._retries):
            try:
                r = httpx.post(self._url, headers=self._headers, timeout=self._timeout, json={
                    "model": self._model, "temperature": 0,
                    "max_tokens": self._max_tokens,
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": user}],
                })
                r.raise_for_status()
                choice = (r.json().get("choices") or [{}])[0]
                content = (choice.get("message") or {}).get("content")
                if content:
                    return content
                # Ran out of budget while reasoning: retrying identically will not
                # help, so fail fast rather than burning the retry allowance.
                if choice.get("finish_reason") == "length":
                    return None
            except Exception:  # noqa: BLE001, S110 - any failure falls through to the retry below
                pass
            if attempt < self._retries - 1:
                time.sleep(self._backoff * (attempt + 1))
        return None

"""Bifrost (OpenAI-compatible) chat client + defensive JSON extraction.

Vendored rather than imported: okf packages are standalone (see okf-dbparse).
"""
from __future__ import annotations

import json
import re
import time
from typing import Protocol

import httpx


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
    def __init__(self, base: str, api_key: str, model: str, timeout_s: int = 300,
                 retries: int = 4, backoff_s: float = 2.0) -> None:
        self._url = base.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}",
                         "User-Agent": "okfzendesk/0.1"}
        self._model = model
        self._timeout = timeout_s
        self._retries = max(1, retries)
        self._backoff = backoff_s

    def complete(self, system: str, user: str) -> str | None:
        # Callers treat None as a hard failure (skip the ticket), so a transient blip
        # must not silently look like a decision.
        for attempt in range(self._retries):
            try:
                r = httpx.post(self._url, headers=self._headers, timeout=self._timeout, json={
                    "model": self._model, "temperature": 0,
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": user}],
                })
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
            except Exception:
                if attempt == self._retries - 1:
                    return None
                time.sleep(self._backoff * (attempt + 1))
        return None

"""Shared glue for the conflict-scoring commands. Private: underscore-prefixed, so it ships
in the wheel with no console script over it.
"""
from __future__ import annotations

import os


def gateway_llm():
    """The conflict-scoring gateway from the environment, or None when it is not configured.

    One definition because two commands must agree on it: `hivegen-memory-conflict-score`
    and `hivegen-pr-conflict-gate` both score with it, and the scorer fails SAFE, so a
    default model updated in one copy and not the other would retire the model under one
    command and turn every candidate pair into a blocking verdict nothing measured. What an
    absent gateway MEANS stays with each caller - the scorer is advisory, the gate refuses.
    """
    base = os.environ.get("BIFROST_BASE")
    key = os.environ.get("BIFROST_API_KEY")
    if not base or not key:
        return None
    from hivegen.llm import BifrostChat
    return BifrostChat(base, key, os.environ.get("CONFLICT_MODEL") or "minimax/minimax-m3")

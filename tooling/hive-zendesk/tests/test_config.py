import os
from pathlib import Path

from hivezendesk.config import Settings


def _s(**kw):
    return Settings(bifrost_base="x", bifrost_api_key="y", **kw)


def test_rerank_model_defaults_to_the_cheap_tier():
    """On a 16-item labelled set Qwen, minimax-m3 and deepseek all scored ~80% and kept
    the SAME wrong links, while anthropic/claude-opus-4.8 scored 92%. Opus is an on-demand
    escalation, so the default reranker is the cheap tier."""
    assert _s().rerank_model == "minimax/minimax-m3"


def test_rerank_model_is_selectable_without_changing_the_distiller():
    """Distilling prose and choosing links are different jobs on different models: the
    corpus is distilled on-prem by Qwen but linked by a hosted model."""
    s = _s(distill_model="local-gw/qwen3.6-27b", rerank_model="anthropic/claude-opus-4.8")
    assert s.distill_model == "local-gw/qwen3.6-27b"
    assert s.rerank_model == "anthropic/claude-opus-4.8"


def test_changing_the_distiller_alone_leaves_the_reranker_on_its_default():
    assert _s(distill_model="local-gw/qwen3.6-27b").rerank_model == "minimax/minimax-m3"


def test_r2_bucket_has_no_default(monkeypatch, tmp_path):
    """It shipped as a real private bucket name. That is two failures at once: everyone who
    installed the wheel could read the bucket out of it, and an operator who never set
    R2_BUCKET read a bucket that was not theirs - which lists nothing, and reads exactly
    like a bucket with nothing staged in it. hive-gen's equivalent has always been empty."""
    monkeypatch.chdir(tmp_path)  # no .env of the developer's own
    monkeypatch.delenv("R2_BUCKET", raising=False)
    assert _s().r2_bucket == ""


# --------------------------------------------------------------------------
# `.env.example` is the file a new operator copies to `.env` as their first step, so a
# value in it that disagrees with `config.py` is a silent override of the shipped
# default rather than a mismatch anyone notices.
# --------------------------------------------------------------------------

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"


def _settings_from_env_example(tmp_path, monkeypatch):
    """Build Settings the way an operator's first run does: .env.example copied to .env."""
    monkeypatch.chdir(tmp_path)
    for key in list(os.environ):
        if key.lower() in Settings.model_fields:
            monkeypatch.delenv(key, raising=False)
    (tmp_path / ".env").write_text(ENV_EXAMPLE.read_text())
    return Settings()


def test_env_example_matches_the_shipped_model_defaults(tmp_path, monkeypatch):
    """OpenRouter has no alias layer, so a bare `minimax-m3` copied out of this file
    reaches a live endpoint and comes back as an unknown model - every linking call fails
    while `config.py` and the docs say the default is provider-qualified."""
    s = _settings_from_env_example(tmp_path, monkeypatch)
    for field in ("distill_model", "rerank_model"):
        assert getattr(s, field) == Settings.model_fields[field].default

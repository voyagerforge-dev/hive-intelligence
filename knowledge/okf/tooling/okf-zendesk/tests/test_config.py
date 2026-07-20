from okfzendesk.config import Settings


def _s(**kw):
    return Settings(bifrost_base="x", bifrost_api_key="y", **kw)


def test_rerank_model_defaults_to_the_cheap_tier():
    """On a 16-item labelled set Qwen, minimax-m3 and deepseek all scored ~80% and kept
    the SAME wrong links, while claude-opus-4-8 scored 92%. Opus is an on-demand
    escalation, so the default reranker is the cheap tier."""
    assert _s().rerank_model == "minimax-m3"


def test_rerank_model_is_selectable_without_changing_the_distiller():
    """Distilling prose and choosing links are different jobs on different models: the
    corpus is distilled on-prem by Qwen but linked by a hosted model."""
    s = _s(distill_model="host-d/qwen3.6-27b", rerank_model="openrouter/claude-opus-4-8")
    assert s.distill_model == "host-d/qwen3.6-27b"
    assert s.rerank_model == "openrouter/claude-opus-4-8"


def test_changing_the_distiller_alone_leaves_the_reranker_on_its_default():
    assert _s(distill_model="host-d/qwen3.6-27b").rerank_model == "minimax-m3"

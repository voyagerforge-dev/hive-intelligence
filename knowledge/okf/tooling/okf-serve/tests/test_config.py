from okfserve.config import get_settings


def test_settings_reads_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    monkeypatch.setenv("BIFROST_BASE", "http://bf/v1")
    monkeypatch.setenv("BIFROST_API_KEY", "k")
    s = get_settings()
    assert s.select_model == "deepseek-v4-flash"
    assert s.answer_model == "minimax-m3"
    assert s.judge_model == "minimax-m3"
    assert s.bifrost_timeout_s == 300
    assert s.max_cards == 8
    assert s.resolve_depth == 1
    get_settings.cache_clear()

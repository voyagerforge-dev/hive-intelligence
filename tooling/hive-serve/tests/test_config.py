from hiveserve.config import Settings, get_settings


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


def test_settings_have_serving_defaults():
    s = Settings()
    assert s.concepts_dir
    assert s.okf_data_dir
    assert s.host == "127.0.0.1"
    assert s.port == 8000
    assert s.transport == "stdio"
    assert s.okf_default_owner
    assert s.identity_header


def test_settings_has_clients_dir():
    from hiveserve.config import Settings
    assert Settings().clients_dir == "../../clients"

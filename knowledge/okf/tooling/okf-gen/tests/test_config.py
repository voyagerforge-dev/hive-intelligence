from okfgen.config import get_settings


def test_settings_reads_env(monkeypatch, tmp_path):
    # Isolate from the developer's real .env: run in a dir with no .env so only
    # the env vars set here apply and the class defaults can be asserted.
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    for k, v in {
        "R2_ENDPOINT": "https://r2", "R2_ACCESS_KEY_ID": "a", "R2_SECRET_ACCESS_KEY": "s",
        "R2_BUCKET": "b", "BIFROST_BASE": "http://bf/v1", "BIFROST_API_KEY": "k",
    }.items():
        monkeypatch.setenv(k, v)
    s = get_settings()
    assert s.r2_prefix == "example_prefix/"
    assert s.taxonomy_model == "minimax-m3"
    assert s.assign_model == "deepseek-v4-flash"
    assert s.max_chars == 24000
    get_settings.cache_clear()

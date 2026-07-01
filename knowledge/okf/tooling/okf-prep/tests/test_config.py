from okfprep.config import Settings, get_settings


def test_settings_defaults(monkeypatch, tmp_path):
    # Isolate from the developer's real .env: run in a dir with no .env so only
    # the env vars set here apply and the class defaults can be asserted.
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.prefer_docling is True
    assert s.vision_min_chars == 100
    assert s.qwen_model  # non-empty default
    assert s.lo_jobs >= 1
    assert s.docling_timeout_s > 0


def test_get_settings(monkeypatch, tmp_path):
    # Verify get_settings() cached function works with env isolation.
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    s = get_settings()
    assert isinstance(s, Settings)
    get_settings.cache_clear()

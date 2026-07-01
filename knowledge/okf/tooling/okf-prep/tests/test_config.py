from okfprep.config import Settings


def test_settings_defaults():
    s = Settings()
    assert s.prefer_docling is True
    assert s.vision_min_chars == 100
    assert s.qwen_model  # non-empty default
    assert s.lo_jobs >= 1
    assert s.docling_timeout_s > 0

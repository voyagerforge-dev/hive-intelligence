from hiveprep.config import Settings, get_settings


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


# --------------------------------------------------------------------------
# .env.example is the file a new operator copies to .env. Every path in it is
# therefore a path someone's first run starts from, which rules out absolute
# paths under one machine's home directory: they are dead everywhere else, and
# a dead ATOMIC_DIR does not fail, it stamps zero files and exits 0.
# --------------------------------------------------------------------------

from pathlib import Path

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"


def _env_example_pairs() -> dict[str, str]:
    pairs = {}
    for line in ENV_EXAMPLE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        pairs[k.strip()] = v.strip()
    return pairs


def test_env_example_has_no_absolute_path_under_a_home_directory():
    for key, value in _env_example_pairs().items():
        assert not value.startswith("/home/"), f"{key} points into one machine's home: {value}"
        assert not value.startswith("/Users/"), f"{key} points into one machine's home: {value}"


def test_env_example_paths_are_either_empty_or_reachable_from_a_fresh_checkout():
    """A relative default works anywhere. An absolute one has to exist, and none of
    these ever will on someone else's machine, so it must be left empty instead."""
    for key in ("CORPUS_ROOT", "WORK_DIR", "ATOMIC_DIR"):
        value = _env_example_pairs().get(key, "")
        assert value == "" or not value.startswith("/"), \
            f"{key}={value} is an absolute path that will not exist for the next operator"


def test_env_example_only_names_real_settings():
    known = set(Settings.model_fields)
    for key in _env_example_pairs():
        assert key.lower() in known, f"{key} is not a hiveprep setting"

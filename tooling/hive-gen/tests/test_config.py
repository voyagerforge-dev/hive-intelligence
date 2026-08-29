from hivegen.config import Settings, get_settings


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


# --------------------------------------------------------------------------
# .env.example is the file a new operator copies to .env. A setting the tool
# refuses to run without therefore has to be IN it: otherwise the refusal
# names a variable that appears nowhere in what they were given. And no path
# in it may be absolute under one machine's home directory, since it is dead
# on every other machine and a dead corpus path does not fail, it finds
# nothing and carries on.
# --------------------------------------------------------------------------

import os
from pathlib import Path

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"


def _pairs() -> dict[str, str]:
    out = {}
    for line in ENV_EXAMPLE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _settings_from_env_example(tmp_path, monkeypatch):
    """Build Settings the way an operator's first run does: .env.example copied to .env."""
    (tmp_path / ".env").write_text(ENV_EXAMPLE.read_text())
    monkeypatch.chdir(tmp_path)
    for key in list(os.environ):
        if key.lower() in Settings.model_fields:
            monkeypatch.delenv(key, raising=False)
    return Settings()


def test_env_example_only_names_real_settings():
    known = set(Settings.model_fields)
    for key in _pairs():
        assert key.lower() in known, f"{key} is not a setting of this package"


def test_env_example_has_no_absolute_path_under_a_home_directory():
    for key, value in _pairs().items():
        assert not value.startswith(("/home/", "/Users/")), \
            f"{key} points into one machine's home: {value}"


def test_a_copied_env_example_leaves_the_card_corpus_root_required_and_unset(tmp_path,
                                                                            monkeypatch):
    """CARD_CORPUS_ROOT aborts the run when unset, so it must be present and empty here:
    present so the operator sees what to fill in, empty because no guess is right."""
    s = _settings_from_env_example(tmp_path, monkeypatch)
    assert "CARD_CORPUS_ROOT" in _pairs()
    assert s.card_corpus_root == ""


def test_env_example_does_not_name_hive_preps_corpus_root():
    """The two are different trees. Naming CORPUS_ROOT here would invite an operator to
    reuse the raw ingest tree as the card corpus, which is a directory and so passes the
    guard - the exact failure the rename removes."""
    assert "CORPUS_ROOT" not in _pairs()

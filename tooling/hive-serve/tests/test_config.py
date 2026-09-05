from hiveserve.config import Settings, get_settings


def test_settings_reads_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    monkeypatch.setenv("BIFROST_BASE", "http://bf/v1")
    monkeypatch.setenv("BIFROST_API_KEY", "k")
    s = get_settings()
    assert s.select_model == "deepseek-v4-flash"
    # deepseek-v4 since 2026-09-06: minimax-m3 is refused by its provider for an
    # exhausted token plan, and a model that never answers reads as correct 0 / grounded 0.
    assert s.answer_model == "deepseek-v4"
    assert s.judge_model == "deepseek-v4"
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


def test_a_copied_env_example_leaves_the_corpus_settings_required_and_unset(tmp_path,
                                                                           monkeypatch):
    """`run_eval` aborts on an unset CONCEPTS_DIR or EVAL_DIR, so both must be present and
    empty here. CLIENTS_DIR is optional but must still be visible: silently disabled client
    memory is how an eval reports a wrong aggregate."""
    s = _settings_from_env_example(tmp_path, monkeypatch)
    pairs = _pairs()
    for key in ("CONCEPTS_DIR", "CLIENTS_DIR", "EVAL_DIR"):
        assert key in pairs, f"{key} is required to run the eval but is not in .env.example"
    assert s.concepts_dir == ""
    assert s.clients_dir == ""
    assert s.eval_dir == ""


def test_a_copied_env_example_does_not_contradict_the_code_defaults(tmp_path, monkeypatch):
    """A value in this file that disagrees with config.py is a silent downgrade for anyone
    who copies it: MAX_CHARS=80000 produced bundles that overran the client's token cap."""
    s = _settings_from_env_example(tmp_path, monkeypatch)
    assert s.max_chars == Settings.model_fields["max_chars"].default
    assert s.max_cards == Settings.model_fields["max_cards"].default
    assert s.resolve_depth == Settings.model_fields["resolve_depth"].default


def test_env_example_matches_the_shipped_model_defaults():
    """A `.env.example` naming a different model from `config.py` makes the documented
    first step - copy it to `.env` - silently change which models the harness calls."""
    from pathlib import Path

    example = dict(
        line.split("=", 1)
        for line in Path(__file__).resolve().parents[1].joinpath(".env.example")
        .read_text().splitlines()
        if "=" in line and not line.startswith("#"))
    s = Settings()
    assert example["SELECT_MODEL"] == s.select_model
    assert example["ANSWER_MODEL"] == s.answer_model
    assert example["JUDGE_MODEL"] == s.judge_model

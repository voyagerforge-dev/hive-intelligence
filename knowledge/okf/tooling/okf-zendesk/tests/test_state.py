from okfzendesk.state import load_state, replay_since, save_state


def test_roundtrip(tmp_path):
    assert load_state(tmp_path, "alpha") == {}
    save_state(tmp_path, "alpha", {"42": "2026-03-14T00:00:00Z"})
    assert load_state(tmp_path, "alpha") == {"42": "2026-03-14T00:00:00Z"}


def test_replay_since_prefers_oldest_unprocessed():
    assert replay_since("2026-03-14T00:00:00Z", "2026-02-01T00:00:00Z") == "2026-02-01T00:00:00Z"


def test_replay_since_falls_back_to_stored_when_nothing_pending():
    assert replay_since("2026-03-14T00:00:00Z", None) == "2026-03-14T00:00:00Z"


def test_replay_since_defaults_to_epoch_when_unset():
    assert replay_since(None, None).startswith("1970")

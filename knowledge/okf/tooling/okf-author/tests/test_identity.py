from okfauthor.config import Settings
from okfauthor.identity import resolve_owner


def test_header_wins_else_default():
    s = Settings()
    assert resolve_owner({"cf-access-authenticated-user-email": "a@x.dev"}, s) == "a@x.dev"
    assert resolve_owner(None, s) == s.okf_default_owner
    assert resolve_owner({}, s) == s.okf_default_owner

from hiveauthor.config import Settings


def test_defaults():
    s = Settings()
    assert s.forge_repo == ""
    assert s.forge_api == ""
    assert s.identity_header == "cf-access-authenticated-user-email"

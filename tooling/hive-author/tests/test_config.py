from hiveauthor.config import Settings


def test_defaults():
    s = Settings()
    assert s.github_repo == ""
    assert s.github_api == "https://api.github.com"
    assert s.identity_header == "cf-access-authenticated-user-email"

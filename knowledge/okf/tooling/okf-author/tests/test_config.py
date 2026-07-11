from okfauthor.config import Settings


def test_defaults():
    s = Settings()
    assert s.github_repo == "example-org/project-hive"
    assert s.github_api == "https://api.github.com"
    assert s.identity_header == "cf-access-authenticated-user-email"

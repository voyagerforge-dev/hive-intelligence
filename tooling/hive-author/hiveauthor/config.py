"""Typed settings for the hive-author write-only MCP server (env / .env backed)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    forge_token: str = ""
    # An alternative to forge_token, for a credential that expires faster than this process
    # lives. A GitHub App installation token lasts an hour, so it cannot be an env var read
    # once at startup. Something else mints one and writes it here; the client re-reads the
    # file on every submission. Set one or the other, not both.
    forge_token_file: str = ""
    # Which forge this deployment files against: "forgejo" or "github". No default, and
    # not inferred from forge_api. Guessing wrong sends label IDs to GitHub or label names
    # to Forgejo, and the submission fails at the moment somebody is waiting on it.
    forge_kind: str = ""
    # No default. This names the corpus repository that card submissions are filed
    # against, which is deployment-specific, and a wrong-but-plausible default files
    # issues into someone else's repository.
    forge_repo: str = ""
    # No default either, and deliberately not a public URL: a default pointing anywhere
    # reachable would let a misconfigured deployment file submissions into a real repository
    # that is not the intended one. Empty fails loudly at startup instead.
    forge_api: str = ""
    host: str = "127.0.0.1"
    port: int = 8000
    identity_header: str = "cf-access-authenticated-user-email"
    okf_default_owner: str = "local-operator"


@lru_cache
def get_settings() -> Settings:
    return Settings()

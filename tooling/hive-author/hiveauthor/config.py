"""Typed settings for the hive-author write-only MCP server (env / .env backed)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    forge_token: str = ""
    # No default. This names the corpus repository that card submissions are filed
    # against, which is deployment-specific, and a wrong-but-plausible default files
    # issues into someone else's repository.
    forge_repo: str = ""
    # No default either, and deliberately not a public URL. The forge is LAN-only, so a
    # default pointing anywhere reachable would let a misconfigured deployment file
    # submissions somewhere real. Empty fails loudly at startup instead.
    forge_api: str = ""
    host: str = "127.0.0.1"
    port: int = 8000
    identity_header: str = "cf-access-authenticated-user-email"
    okf_default_owner: str = "local-operator"


@lru_cache
def get_settings() -> Settings:
    return Settings()

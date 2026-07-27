"""Typed settings for the hive-author write-only MCP server (env / .env backed)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    github_token: str = ""
    github_repo: str = "example-org/project-hive"
    github_api: str = "https://api.github.com"
    host: str = "127.0.0.1"
    port: int = 8000
    identity_header: str = "cf-access-authenticated-user-email"
    okf_default_owner: str = "local-operator"


@lru_cache
def get_settings() -> Settings:
    return Settings()

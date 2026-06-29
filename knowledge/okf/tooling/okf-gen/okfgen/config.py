"""Typed settings for the OKF card pipeline (env / .env backed)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    r2_endpoint: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket: str
    r2_prefix: str = "example_prefix/"

    bifrost_base: str
    bifrost_api_key: str
    taxonomy_model: str = "minimax-m3"
    assign_model: str = "deepseek-v4-flash"
    distill_model: str = "minimax-m3"
    max_chars: int = 24000


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

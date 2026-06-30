"""Typed settings for the OKF serving + eval package (env / .env backed)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bifrost_base: str = ""
    bifrost_api_key: str = ""
    select_model: str = "deepseek-v4-flash"
    answer_model: str = "minimax-m3"
    judge_model: str = "minimax-m3"
    bifrost_timeout_s: int = 300
    max_cards: int = 8
    max_chars: int = 80000
    resolve_depth: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()

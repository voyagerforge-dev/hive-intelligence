"""Typed settings for the OKF card pipeline (env / .env backed)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Local atomic-markdown source (scpp-prep never writes markdown to R2, so the
    # curated atomic markdown lives on disk). When set, it is the source of truth
    # and R2 is not read. Leave empty to fall back to the R2 reader.
    atomic_dir: str = ""

    r2_endpoint: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    r2_prefix: str = "example_prefix/"

    bifrost_base: str
    bifrost_api_key: str
    taxonomy_model: str = "minimax-m3"
    assign_model: str = "deepseek-v4-flash"
    distill_model: str = "minimax-m3"
    max_chars: int = 24000
    # minimax-m3 (reasoning) can take >150s for a large taxonomy/distill response;
    # the client timeout must exceed that or every retry times out → 0 results.
    bifrost_timeout_s: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

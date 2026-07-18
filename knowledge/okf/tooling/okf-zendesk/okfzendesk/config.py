"""Settings. Mirrors okf-gen's pydantic-settings pattern."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    connector_base: str = "http://hive-host.internal:8014"
    connector_api_key: str = ""
    bifrost_base: str = ""
    bifrost_api_key: str = ""
    distill_model: str = "minimax-m3"
    bifrost_timeout_s: int = 300
    # The connector caps a pull at max_pages(30) * page_size(100).
    connector_page_cap: int = 3000
    # Treat >= this fraction of the cap as "probably truncated".
    cap_warn_ratio: float = 0.95

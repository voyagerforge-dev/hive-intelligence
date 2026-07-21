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
    # 40K chars is ~10K tokens. The old 80K produced ~18K-token bundles that overran the
    # MCP client's per-result token cap and spilled to a file, forcing chunked re-reads.
    max_chars: int = 40000
    resolve_depth: int = 1
    concepts_dir: str = "../../concepts"
    clients_dir: str = "../../clients"
    okf_data_dir: str = "./.data"
    host: str = "127.0.0.1"
    port: int = 8000
    transport: str = "stdio"
    okf_default_owner: str = "local-operator"
    identity_header: str = "x-forwarded-email"


@lru_cache
def get_settings() -> Settings:
    return Settings()

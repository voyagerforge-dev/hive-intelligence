"""Typed settings for the OKF serving + eval package (env / .env backed)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bifrost_base: str = ""
    bifrost_api_key: str = ""
    # Evaluation harness only; serving makes no model calls. Provider ids, not gateway
    # aliases: the estate calls OpenRouter directly since 2026-09-06 and OpenRouter has
    # no alias layer, so a bare `deepseek-v4-flash` resolves nowhere. Dated ids also say
    # which release produced a report, which an undated alias never did.
    select_model: str = "deepseek/deepseek-v4-flash-0731"
    answer_model: str = "deepseek/deepseek-v4-pro"
    judge_model: str = "deepseek/deepseek-v4-pro"
    bifrost_timeout_s: int = 300
    max_cards: int = 8
    # 40K chars is ~10K tokens. The old 80K produced ~18K-token bundles that overran the
    # MCP client's per-result token cap and spilled to a file, forcing chunked re-reads.
    max_chars: int = 40000
    resolve_depth: int = 1
    concepts_dir: str = "../../concepts"
    clients_dir: str = "../../clients"
    # Labelled eval sets, for the evaluation harness only. No default, deliberately: sets
    # name real card ids, so they ship with a corpus and there is nowhere here they could
    # plausibly be. A bare qa-set name used to resolve inside this package, a directory
    # the 2026-08-11 corpus split removed.
    eval_dir: str = ""
    # Retained: hive-serve still writes non-ledger scratch here. The LEDGER no longer
    # lives in it, see ledger_dsn below.
    okf_data_dir: str = "./.data"
    # The objective/memory ledger, Postgres since 2026-08-19. No default, deliberately:
    # the previous setting defaulted to a path, so a misconfigured deployment quietly got
    # a fresh empty SQLite file and served an empty ledger while looking healthy. An empty
    # DSN now fails at startup instead.
    ledger_dsn: str = ""
    host: str = "127.0.0.1"
    port: int = 8000
    transport: str = "stdio"
    okf_default_owner: str = "local-operator"
    identity_header: str = "x-forwarded-email"


@lru_cache
def get_settings() -> Settings:
    return Settings()

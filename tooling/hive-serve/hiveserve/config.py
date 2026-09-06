"""Typed settings for the OKF serving + eval package (env / .env backed)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bifrost_base: str = ""
    bifrost_api_key: str = ""
    # Evaluation harness only; serving makes no model calls. Provider ids, not gateway
    # aliases: the estate calls OpenRouter directly since 2026-09-06 and OpenRouter has
    # no alias layer, so an id missing that prefix - `deepseek-v4-flash` rather than
    # `deepseek/deepseek-v4-flash` - resolves nowhere.
    #
    # Selection stays on the April release, not the dated July 31 one that was asked for: on 16 real
    # selection prompts 0731 produced a usable `card_ids` list 0 times against this
    # one's 16, emitting a different JSON schema (`doc_id`, `score`) or nothing at all.
    #
    # The id below carries no date suffix, and is provider-qualified already. Observed on
    # OpenRouter 2026-09-06: `deepseek/deepseek-v4-flash` and the `-0731` id were separate
    # catalogue entries, created 2026-04-24 and 2026-07-31 with different context windows,
    # and the floating alias carried a distinct `-latest` name - so the undated id named
    # the April release rather than tracking the newest Flash. That catalogue is a third
    # party's and nothing here can check it: if those entries are ever collapsed or the
    # undated id repointed, selection moves onto the rejected release with no error, so
    # re-read the catalogue rather than trusting this note.
    select_model: str = "deepseek/deepseek-v4-flash"
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

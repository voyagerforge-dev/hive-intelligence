"""Settings. Mirrors hive-gen's pydantic-settings pattern."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # No default. A connector address belongs to a deployment, and a plausible-looking
    # default fails late and against the wrong host rather than at startup.
    connector_base: str = ""
    connector_api_key: str = ""
    bifrost_base: str = ""
    bifrost_api_key: str = ""
    # No default. An environment that fails to load .env would otherwise distil an
    # entire run with a different model than intended, silently, and the cards would
    # carry no sign of it.
    distill_model: str = ""
    # Linking is a separate job from distilling and is measured separately. On a 16-item
    # labelled set Qwen, minimax-m3 and deepseek all scored ~80% and kept the SAME wrong
    # links, while anthropic/claude-opus-4.8 scored 92% - a capability cliff, not a
    # gradient. So the cheap tier is the default and Opus is an on-demand escalation,
    # not the norm.
    # Provider-qualified since 2026-09-06: OpenRouter is called directly and has no
    # alias layer, so a bare `minimax-m3` resolves nowhere.
    rerank_model: str = "minimax/minimax-m3"
    bifrost_timeout_s: int = 300
    # The on-prem Qwen is a reasoning model: this budget must cover thinking AND the
    # answer. At 2000 it spends the lot reasoning and returns nothing.
    distill_max_tokens: int = 4000
    # The connector caps a pull at max_pages(30) * page_size(100).
    connector_page_cap: int = 3000
    # Treat >= this fraction of the cap as "probably truncated".
    cap_warn_ratio: float = 0.95
    # R2: the retired service's staged cards, reused instead of re-distilling. The bucket
    # has no default. It named a real private bucket, which disclosed that bucket to
    # everyone who installed the package and let an operator who never set R2_BUCKET read
    # one that was not theirs. hive-gen's equivalent setting has always been empty; this
    # makes the two consistent rather than inventing a convention. `run.py` refuses in
    # rebuild mode, naming the setting.
    r2_endpoint: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    # Concurrency for the reshape step. vLLM batches well; the connector is untouched
    # here (one list call per org), so this only loads the LLM.
    reshape_workers: int = 6
    # Cards per LLM call. 5 measured 2.4x fewer tokens/entry than 1; larger batches
    # risk a long single request and an all-or-nothing parse.
    reshape_batch_size: int = 5

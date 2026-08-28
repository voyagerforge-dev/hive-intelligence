"""Typed settings for the OKF card pipeline (env / .env backed)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Local atomic-markdown source (hive-prep never writes markdown to object storage, so the
    # curated atomic markdown lives on disk). When set, it is the source of truth
    # and R2 is not read. Leave empty to fall back to the R2 reader.
    atomic_dir: str = ""

    # The card corpus working tree: where the taxonomies, drafts/ and .pipeline/ for a
    # generation pass live, and the concepts/ hive-serve then serves. Named for WHICH tree
    # it is: hive-prep's CORPUS_ROOT is the raw documents going in, this is the cards coming
    # out, and one exported CORPUS_ROOT would otherwise serve both. No default, deliberately.
    # The corpus is a separate repository (since 2026-08-11) and this used to be derived by
    # walking up from __file__, which after the split landed in the engine repository.
    # Nothing failed: the gate-1 lookup found no approved taxonomy there and re-proposed
    # one from scratch on every run.
    card_corpus_root: str = ""

    # Which functional-area slice to generate. Names an area or sub-area defined by the
    # corpus profile. Empty means the whole corpus in one taxonomy, which is rarely what
    # you want: a taxonomy call spanning everything produces a poor taxonomy.
    slice_area: str = ""

    # Path to the corpus profile (domain vocabulary). Empty means look for
    # corpus-profile.yaml in the working directory, then beside ATOMIC_DIR.
    corpus_profile: str = ""

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

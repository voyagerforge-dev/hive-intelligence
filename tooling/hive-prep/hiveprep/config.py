"""Typed settings for the OKF doc-prep pipeline (env / .env backed)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Filesystem: raw corpus in, work intermediates, atomic markdown out.
    corpus_root: str = ""
    work_dir: str = "./hive-work"
    atomic_dir: str = "./hive-work/atomic"

    # Docling (Host-A GPU), preferred text-tier converter. Empty base → pymupdf4llm only.
    docling_base: str = ""
    docling_api_key: str = ""
    docling_timeout_s: int = 300
    docling_ca_bundle: str = ""
    prefer_docling: bool = True

    # Qwen3.6-27B (Host-D), vision tier (OpenAI-compatible /v1/chat/completions with image_url).
    qwen_base: str = ""
    qwen_api_key: str = ""
    qwen_model: str = "qwen3.6-27b"
    qwen_timeout_s: int = 600

    # Routing: avg extractable chars/page >= this → text tier; below + image-dominant → vision.
    vision_min_chars: int = 100
    # LibreOffice parallel workers for normalize.
    lo_jobs: int = 8

    # Boilerplate stripping, scrub copyright/trademark/confidentiality/page-number noise from
    # converted markdown before it is written as an atomic doc. strip_product selects the
    # <product>.yaml ruleset (falls back to default.yaml). Set strip_boilerplate=false to disable.
    strip_boilerplate: bool = True
    # "default" is the generic rule set. Vendor-specific rules live in a
    # <product>.yaml beside it and are opt-in: a rule set tuned for one vendor's
    # boilerplate will happily delete another's prose.
    strip_product: str = "default"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

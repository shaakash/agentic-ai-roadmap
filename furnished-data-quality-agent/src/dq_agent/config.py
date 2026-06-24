"""Typed, env-driven configuration.

A single `Settings` object sourced from environment / `.env`, plus a `get_llm()`
factory. The LLM is used ONLY for explanations, drafting, and rule hypotheses -
never for anomaly detection (that is the deterministic rule engine).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Data ---
    duckdb_path: str = "data/dq.duckdb"
    batches_path: str = "data/batches"
    gen_seed: int = 42
    gen_num_batches: int = 5
    gen_records_per_batch: int = 2000
    gen_anomaly_rate: float = 0.06

    # --- Rule engine (deterministic core) ---
    rules_path: str = "src/dq_agent/rules/rules.yaml"
    severity_block_threshold: str = "high"

    # --- LLM (assistance only; never detection) ---
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = "replace-me"
    llm_temperature: float = 0.0

    # --- Generated-code sandbox ---
    sandbox_enabled: bool = True
    sandbox_timeout_seconds: int = 5
    rule_promotion_min_precision: float = 0.95
    rule_promotion_min_recall: float = 0.80

    # --- Governance ---
    hitl_required: bool = True
    email_autosend: bool = False

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- Observability ---
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "furnished-data-quality-agent"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


def get_llm(temperature: float | None = None):
    """Return a configured chat model for explanations/drafting/hypotheses.

    Kept thin and lazy so importing this module does not require the LLM stack or
    an API key (the deterministic core and tests must run without it).
    """
    from langchain_openai import ChatOpenAI

    s = get_settings()
    return ChatOpenAI(
        model=s.llm_model,
        api_key=s.llm_api_key,
        temperature=s.llm_temperature if temperature is None else temperature,
    )

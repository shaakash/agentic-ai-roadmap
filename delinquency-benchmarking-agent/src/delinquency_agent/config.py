"""Typed, env-driven configuration — reads from .env and environment variables.

Usage::

    from delinquency_agent.config import get_settings, get_llm

    settings = get_settings()           # cached after first call
    llm      = get_llm()                # ChatOpenAI (or other provider) at temperature 0

The OPENAI_API_KEY must be set in the environment (or in .env) before calling
get_llm(). All other fields have sensible defaults.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration read from environment / .env file.

    pydantic-settings maps environment variable names case-insensitively, so
    DUCKDB_PATH=... in the shell sets duckdb_path here automatically.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",           # silently ignore unknown env vars
    )

    # ── Data layer ────────────────────────────────────────────────────────
    duckdb_path:      str   = "data/benchmark.duckdb"
    gen_seed:         int   = 42
    gen_start_month:  str   = "2023-01"
    gen_num_months:   int   = 24
    gen_num_members:  int   = 18

    # ── Knowledge / RAG ───────────────────────────────────────────────────
    chroma_path:  str = "data/chroma"
    corpus_path:  str = "corpus/definitions"

    # ── LLM (planning + narration only; never touches numbers) ────────────
    llm_provider:    str   = "openai"
    llm_model:       str   = "gpt-4o-mini"
    llm_temperature: float = 0.0

    # ── Governance ────────────────────────────────────────────────────────
    min_cell_members:      int = 5
    default_entitlement:   str = "industry_only"
    grounding_rel_tolerance: float = 0.01   # 1% relative tolerance for number matching

    # ── API ───────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ── Observability ─────────────────────────────────────────────────────
    otel_service_name:             str = "delinquency-benchmarking-agent"
    otel_exporter_otlp_endpoint:   str = ""     # empty → ConsoleSpanExporter


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (reads .env on first call)."""
    return Settings()


def get_llm(settings: Settings | None = None):
    """Return a configured LangChain chat model ready for structured output.

    Raises:
        EnvironmentError: if OPENAI_API_KEY is not set (for openai provider).
        ImportError:      if langchain-openai is not installed.
        ValueError:       if llm_provider is not supported.

    The returned object is a LangChain BaseChatModel. Callers use
    `llm.with_structured_output(SomePydanticModel)` for tool-calling nodes.
    """
    s = settings or get_settings()

    if s.llm_provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise ImportError(
                "langchain-openai is not installed. "
                "Run: pip install langchain-openai"
            ) from exc

        if not os.environ.get("OPENAI_API_KEY"):
            raise EnvironmentError(
                "OPENAI_API_KEY is not set.\n"
                "  • Add OPENAI_API_KEY=sk-... to your .env file, or\n"
                "  • export OPENAI_API_KEY=sk-... in your shell."
            )

        return ChatOpenAI(model=s.llm_model, temperature=s.llm_temperature)

    raise ValueError(
        f"Unsupported llm_provider: '{s.llm_provider}'. "
        "Supported values: openai"
    )

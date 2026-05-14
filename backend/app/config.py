"""Settings — single import everywhere. Loaded once at startup.

Env vars are validated by Pydantic; missing required values fail fast at boot.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. Values come from env (see .env.example)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Database ---
    database_url: str = Field(
        default="postgresql+psycopg://sift:sift@localhost:5432/sift",
        alias="DATABASE_URL",
    )

    # --- LLM ---
    # Default `stub` so a fresh checkout works with no API key (interview review).
    # Set to `anthropic` (plus ANTHROPIC_API_KEY) for real model calls.
    llm_provider: Literal["stub", "anthropic"] = Field(default="stub", alias="SIFT_LLM_PROVIDER")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    model_tier_1: str = Field(default="claude-haiku-4-5", alias="SIFT_MODEL_TIER_1")
    model_tier_2: str = Field(default="claude-sonnet-4-6", alias="SIFT_MODEL_TIER_2")
    model_tier_3: str = Field(default="claude-opus-4-7", alias="SIFT_MODEL_TIER_3")

    # --- Storage ---
    upload_dir: Path = Field(default=Path("./uploads"), alias="SIFT_UPLOAD_DIR")

    # --- Logging ---
    log_level: str = Field(default="INFO", alias="SIFT_LOG_LEVEL")
    log_format: str = Field(default="json", alias="SIFT_LOG_FORMAT")

    # --- CORS ---
    cors_origins_raw: str = Field(default="http://localhost:5173", alias="SIFT_CORS_ORIGINS")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor — read once, reused everywhere."""
    return Settings()

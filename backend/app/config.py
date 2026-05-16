"""Settings — single import everywhere. Loaded once at startup.

Env vars are validated by Pydantic; missing required values fail fast at boot.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
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

    database_url: str = Field(
        default="postgresql+psycopg://sift:sift@localhost:5432/sift",
        alias="DATABASE_URL",
    )

    llm_provider: Literal["stub", "anthropic"] = Field(default="stub", alias="SIFT_LLM_PROVIDER")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    model_tier_1: str = Field(default="claude-haiku-4-5", alias="SIFT_MODEL_TIER_1")
    model_tier_2: str = Field(default="claude-sonnet-4-6", alias="SIFT_MODEL_TIER_2")
    model_tier_3: str = Field(default="claude-opus-4-7", alias="SIFT_MODEL_TIER_3")

    api_budget_usd: float = Field(default=5.0, alias="SIFT_API_BUDGET_USD")

    upload_dir: Path = Field(default=Path("./uploads"), alias="SIFT_UPLOAD_DIR")

    blob_store: Literal["local", "r2"] = Field(default="local", alias="SIFT_BLOB_STORE")
    r2_account_id: str = Field(default="", alias="SIFT_R2_ACCOUNT_ID")
    r2_access_key_id: str = Field(default="", alias="SIFT_R2_ACCESS_KEY_ID")
    r2_secret_access_key: str = Field(default="", alias="SIFT_R2_SECRET_ACCESS_KEY")
    r2_bucket: str = Field(default="", alias="SIFT_R2_BUCKET")

    log_level: str = Field(default="INFO", alias="SIFT_LOG_LEVEL")
    log_format: str = Field(default="json", alias="SIFT_LOG_FORMAT")

    cors_origins_raw: str = Field(default="http://localhost:5173", alias="SIFT_CORS_ORIGINS")

    secret_key: str = Field(
        default="dev-only-secret-do-not-use-in-prod",
        alias="SIFT_SECRET_KEY",
    )
    cookie_secure: bool = Field(default=False, alias="SIFT_COOKIE_SECURE")
    session_remember_days: int = Field(default=30, alias="SIFT_SESSION_REMEMBER_DAYS")
    session_default_hours: int = Field(default=12, alias="SIFT_SESSION_DEFAULT_HOURS")
    demo_email: str = Field(default="ap-clerk@sift.demo", alias="SIFT_DEMO_EMAIL")
    demo_password: str = Field(default="letmein-demo", alias="SIFT_DEMO_PASSWORD")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]

    @property
    def using_dev_secret(self) -> bool:
        return self.secret_key == "dev-only-secret-do-not-use-in-prod"

    @model_validator(mode="after")
    def _r2_requires_credentials(self) -> "Settings":
        if self.blob_store == "r2":
            missing = [
                name for name, val in [
                    ("r2_account_id", self.r2_account_id),
                    ("r2_access_key_id", self.r2_access_key_id),
                    ("r2_secret_access_key", self.r2_secret_access_key),
                    ("r2_bucket", self.r2_bucket),
                ] if not val
            ]
            if missing:
                raise ValueError(f"blob_store=r2 requires: {', '.join(missing)}")
        return self

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor — read once, reused everywhere."""
    return Settings()

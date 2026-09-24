"""Typed application configuration loaded exclusively from the environment."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    """Supported execution environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings with mandatory, validated infrastructure values."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    app_env: AppEnvironment
    database_url: SecretStr
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    pdf_storage_root: Path = Path("storage/pdf-imports")

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: SecretStr) -> SecretStr:
        """Reject accidental use of a local-file database or unsupported scheme."""

        url = value.get_secret_value()
        if not url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL deve usar PostgreSQL")
        return value

    @property
    def is_production(self) -> bool:
        """Return whether production-only controls should be enabled."""

        return self.app_env is AppEnvironment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    """Load and cache settings without logging their values."""

    return Settings()  # type: ignore[call-arg]

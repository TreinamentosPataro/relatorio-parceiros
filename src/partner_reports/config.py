"""Typed application configuration loaded exclusively from the environment."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    """Supported execution environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class PdfDataScope(StrEnum):
    """Data scope deliberately available in the current release."""

    SYNTHETIC_ONLY = "synthetic_only"
    PRIVATE_PILOT = "private_pilot"


class Settings(BaseSettings):
    """Application settings with mandatory, validated infrastructure values."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
        # Validation errors reach container logs; never echo raw values such as DATABASE_URL.
        hide_input_in_errors=True,
    )

    app_env: AppEnvironment
    database_url: SecretStr
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    pdf_storage_root: Path = Path("storage/pdf-imports")
    report_storage_root: Path = Path("output")
    pdf_four_eyes: bool = True
    pdf_synthetic_corrections: bool = False
    pdf_data_scope: PdfDataScope = PdfDataScope.SYNTHETIC_ONLY
    # Retired allowlist, kept only so a stale value fails closed instead of being ignored.
    pdf_pilot_partner_ids: SecretStr = SecretStr("")

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: SecretStr) -> SecretStr:
        """Reject accidental use of a local-file database or unsupported scheme."""

        url = value.get_secret_value()
        if not url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL deve usar PostgreSQL")
        return value

    @model_validator(mode="after")
    def validate_data_scope(self) -> "Settings":
        """Keep real-data admission explicit and fail-closed.

        Real partners are admitted one by one through an audited flag in the database;
        the retired environment allowlist must not linger silently in a deployment.
        """

        if self.pdf_pilot_partner_ids.get_secret_value():
            raise ValueError(
                "PDF_PILOT_PARTNER_IDS foi removida; libere cada parceiro no portal administrativo"
            )
        if self.pdf_data_scope is PdfDataScope.PRIVATE_PILOT and self.app_env not in (
            AppEnvironment.TEST,
            AppEnvironment.PRODUCTION,
        ):
            raise ValueError("private_pilot exige ambiente test ou production")
        return self

    @property
    def is_production(self) -> bool:
        """Return whether production-only controls should be enabled."""

        return self.app_env is AppEnvironment.PRODUCTION

    @property
    def is_deployed(self) -> bool:
        """Return whether internet-facing deployment controls must be enabled."""

        return self.app_env in (AppEnvironment.STAGING, AppEnvironment.PRODUCTION)

    @property
    def synthetic_validation_only(self) -> bool:
        """Return the fail-closed data scope supported by this release."""

        return self.pdf_data_scope is PdfDataScope.SYNTHETIC_ONLY


@lru_cache
def get_settings() -> Settings:
    """Load and cache settings without logging their values."""

    return Settings()  # type: ignore[call-arg]

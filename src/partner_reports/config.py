"""Typed application configuration loaded exclusively from the environment."""

import re
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
    )

    app_env: AppEnvironment
    database_url: SecretStr
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    pdf_storage_root: Path = Path("storage/pdf-imports")
    report_storage_root: Path = Path("output")
    pdf_four_eyes: bool = True
    pdf_synthetic_corrections: bool = False
    pdf_data_scope: PdfDataScope = PdfDataScope.SYNTHETIC_ONLY
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
        """Keep real-data admission explicit, allowlisted and fail-closed."""

        raw = self.pdf_pilot_partner_ids.get_secret_value()
        entries = raw.split(",") if raw else []
        if any(entry != entry.strip() or not entry for entry in entries):
            raise ValueError("PDF_PILOT_PARTNER_IDS deve usar IDs opacos separados por vírgula")
        if any(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", entry) is None for entry in entries
        ):
            raise ValueError("PDF_PILOT_PARTNER_IDS contém identificador inválido")
        if len(entries) != len(set(entries)):
            raise ValueError("PDF_PILOT_PARTNER_IDS contém identificador repetido")
        if self.pdf_data_scope is PdfDataScope.SYNTHETIC_ONLY and entries:
            raise ValueError("allowlist real exige PDF_DATA_SCOPE=private_pilot")
        if self.pdf_data_scope is PdfDataScope.PRIVATE_PILOT:
            if self.app_env not in (AppEnvironment.TEST, AppEnvironment.PRODUCTION):
                raise ValueError("private_pilot exige ambiente test ou production")
            if not entries:
                raise ValueError("private_pilot exige PDF_PILOT_PARTNER_IDS")
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

    @property
    def pilot_partner_ids(self) -> frozenset[str]:
        """Return the opaque private-pilot allowlist without logging its source."""

        raw = self.pdf_pilot_partner_ids.get_secret_value()
        return frozenset(raw.split(",")) if raw else frozenset()

    def partner_is_in_data_scope(self, external_id: str) -> bool:
        """Authorize one partner identifier for the configured data scope."""

        if self.pdf_data_scope is PdfDataScope.SYNTHETIC_ONLY:
            return external_id.startswith("SYNTHETIC-")
        return external_id in self.pilot_partner_ids


@lru_cache
def get_settings() -> Settings:
    """Load and cache settings without logging their values."""

    return Settings()  # type: ignore[call-arg]

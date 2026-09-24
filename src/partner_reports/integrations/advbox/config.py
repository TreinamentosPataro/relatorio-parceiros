"""Dedicated configuration for isolated Advbox read-only commands."""

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdvboxAuditSettings(BaseSettings):
    """Load only the values needed by the read-only API client."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    advbox_api_base_url: AnyHttpUrl = AnyHttpUrl("https://app.advbox.com.br/api/v1")
    advbox_api_token: SecretStr
    advbox_audit_requests_per_minute: int = Field(default=20, ge=1, le=20)
    advbox_audit_timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)
    advbox_audit_max_retries: int = Field(default=3, ge=0, le=5)

    @field_validator("advbox_api_base_url")
    @classmethod
    def require_https(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        """Forbid sending the bearer token over plaintext HTTP."""

        if value.scheme != "https":
            raise ValueError("ADVBOX_API_BASE_URL deve usar HTTPS")
        return value

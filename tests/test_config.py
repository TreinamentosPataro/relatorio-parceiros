"""Configuration validation tests."""

import pytest
from pydantic import ValidationError

from partner_reports.config import AppEnvironment, Settings

VALID_DATABASE_URL = "postgresql+psycopg://synthetic:synthetic@db:5432/synthetic"


def test_settings_load_typed_values_without_exposing_secret() -> None:
    settings = Settings(
        app_env="test",
        database_url=VALID_DATABASE_URL,
        _env_file=None,
    )

    assert settings.app_env is AppEnvironment.TEST
    assert settings.log_level == "INFO"
    assert VALID_DATABASE_URL not in repr(settings)


def test_settings_fail_clearly_when_database_url_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError) as error:
        Settings(app_env="test", _env_file=None)

    assert "database_url" in str(error.value)


def test_settings_reject_non_postgresql_database() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL deve usar PostgreSQL"):
        Settings(
            app_env="test",
            database_url="sqlite:///local.db",
            _env_file=None,
        )

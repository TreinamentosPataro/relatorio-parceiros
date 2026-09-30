"""Configuration validation tests."""

import pytest
from pydantic import ValidationError

from partner_reports.config import AppEnvironment, PdfDataScope, Settings

VALID_DATABASE_URL = "postgresql+psycopg://synthetic:synthetic@db:5432/synthetic"


def test_settings_load_typed_values_without_exposing_secret() -> None:
    settings = Settings(
        app_env="test",
        database_url=VALID_DATABASE_URL,
        _env_file=None,
    )

    assert settings.app_env is AppEnvironment.TEST
    assert settings.pdf_data_scope is PdfDataScope.SYNTHETIC_ONLY
    assert settings.synthetic_validation_only
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


def test_settings_reject_unimplemented_real_data_scope() -> None:
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            database_url=VALID_DATABASE_URL,
            pdf_data_scope="real_private",
            _env_file=None,
        )


def test_validation_errors_never_echo_raw_configuration(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "mysql://synthetic:SYNTHETIC-SECRET-PW@db/synthetic")

    with pytest.raises(ValidationError, match="DATABASE_URL deve usar PostgreSQL") as error:
        Settings(_env_file=None)

    assert "SYNTHETIC-SECRET-PW" not in str(error.value)


def test_private_pilot_admits_partners_through_database_flag_only() -> None:
    settings = Settings(
        app_env="production",
        database_url=VALID_DATABASE_URL,
        pdf_data_scope="private_pilot",
        _env_file=None,
    )

    assert settings.pdf_data_scope is PdfDataScope.PRIVATE_PILOT
    assert not settings.synthetic_validation_only


def test_private_pilot_is_restricted_to_test_or_production() -> None:
    with pytest.raises(ValidationError, match="private_pilot exige ambiente test ou production"):
        Settings(
            app_env="staging",
            database_url=VALID_DATABASE_URL,
            pdf_data_scope="private_pilot",
            _env_file=None,
        )


@pytest.mark.parametrize("scope", ["synthetic_only", "private_pilot"])
def test_retired_environment_allowlist_fails_closed(scope: str) -> None:
    with pytest.raises(ValidationError, match="PDF_PILOT_PARTNER_IDS foi removida") as error:
        Settings(
            app_env="production",
            database_url=VALID_DATABASE_URL,
            pdf_data_scope=scope,
            pdf_pilot_partner_ids="PILOT-001",
            _env_file=None,
        )
    assert "PILOT-001" not in str(error.value)

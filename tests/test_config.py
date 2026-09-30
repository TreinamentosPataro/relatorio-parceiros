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


def test_private_pilot_requires_explicit_opaque_allowlist() -> None:
    with pytest.raises(ValidationError, match="private_pilot exige PDF_PILOT_PARTNER_IDS"):
        Settings(
            app_env="production",
            database_url=VALID_DATABASE_URL,
            pdf_data_scope="private_pilot",
            _env_file=None,
        )

    settings = Settings(
        app_env="production",
        database_url=VALID_DATABASE_URL,
        pdf_data_scope="private_pilot",
        pdf_pilot_partner_ids="PILOT-001,PILOT-002",
        _env_file=None,
    )

    assert settings.pdf_data_scope is PdfDataScope.PRIVATE_PILOT
    assert not settings.synthetic_validation_only
    assert settings.pilot_partner_ids == {"PILOT-001", "PILOT-002"}
    assert settings.partner_is_in_data_scope("PILOT-001")
    assert not settings.partner_is_in_data_scope("PILOT-003")
    assert "PILOT-001" not in repr(settings)


@pytest.mark.parametrize(
    ("environment", "partner_ids", "message"),
    [
        ("staging", "PILOT-001", "private_pilot exige ambiente test ou production"),
        ("production", "PILOT-001, PILOT-002", "IDs opacos separados por vírgula"),
        ("production", "PILOT-001,PILOT-001", "identificador repetido"),
        ("production", "nome com espaço", "identificador inválido"),
    ],
)
def test_private_pilot_rejects_unsafe_configuration(
    environment: str, partner_ids: str, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(
            app_env=environment,
            database_url=VALID_DATABASE_URL,
            pdf_data_scope="private_pilot",
            pdf_pilot_partner_ids=partner_ids,
            _env_file=None,
        )


def test_synthetic_scope_rejects_misleading_real_allowlist() -> None:
    with pytest.raises(ValidationError, match="allowlist real exige"):
        Settings(
            app_env="production",
            database_url=VALID_DATABASE_URL,
            pdf_pilot_partner_ids="PILOT-001",
            _env_file=None,
        )

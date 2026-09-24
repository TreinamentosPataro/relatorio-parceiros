"""Health route tests."""

from fastapi.testclient import TestClient

from partner_reports.config import Settings
from partner_reports.main import create_app


def test_health_returns_only_public_liveness_status() -> None:
    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://synthetic:synthetic@db:5432/synthetic",
        _env_file=None,
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "database" not in response.text.lower()
    assert "synthetic" not in response.text.lower()

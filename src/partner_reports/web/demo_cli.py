"""Seed only named synthetic portal rows linked to already generated previews."""

from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select

from partner_reports.config import AppEnvironment, get_settings
from partner_reports.persistence.database import get_session_factory
from partner_reports.persistence.models import Partner, ReportVersion, SyntheticPortfolio
from partner_reports.web.artifacts import SyntheticArtifactStore

_DEMO = (
    ("SYNTHETIC-ZERO", "Parceiro Exemplo · Carteira vazia", "synthetic/zero"),
    ("SYNTHETIC-ONE", "Parceiro Exemplo · Carteira individual", "synthetic/one"),
    ("SYNTHETIC-MANY", "Parceiro Exemplo · Carteira ampliada", "synthetic/many"),
    ("SYNTHETIC-PENDING", "Parceiro Exemplo · Sem relatório", None),
)


def main() -> None:
    settings = get_settings()
    if settings.app_env is not AppEnvironment.DEVELOPMENT:
        raise SystemExit("Seed sintético permitido apenas em desenvolvimento")
    store = SyntheticArtifactStore(Path("output"), settings.app_env)
    for _, _, key in _DEMO:
        if key:
            store.read(key, "html")
            store.read(key, "pdf")
    with get_session_factory()() as db, db.begin():
        for code, name, key in _DEMO:
            partner = db.scalar(select(Partner).where(Partner.external_id == code))
            if partner is None:
                partner = Partner(external_id=code, name=name, status="active")
                db.add(partner)
                db.flush()
            source = db.scalar(
                select(SyntheticPortfolio).where(SyntheticPortfolio.partner_id == partner.id)
            )
            if source is None:
                db.add(
                    SyntheticPortfolio(
                        partner_id=partner.id,
                        scenario=code.removeprefix("SYNTHETIC-").lower()
                        if code != "SYNTHETIC-PENDING"
                        else "zero",
                        revision=1,
                    )
                )
            if key and not db.scalar(
                select(ReportVersion.id).where(ReportVersion.partner_id == partner.id)
            ):
                db.add(
                    ReportVersion(
                        partner_id=partner.id,
                        period_start=date(2026, 9, 1),
                        period_end=date(2026, 9, 16),
                        version=1,
                        status="validated",
                        generated_at=datetime(2026, 9, 16, 12, 1, tzinfo=UTC),
                        storage_object_key=key,
                    )
                )
    print("Carteiras e versões sintéticas registradas; nenhum dado real foi carregado.")


if __name__ == "__main__":
    main()

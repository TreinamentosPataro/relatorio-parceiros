"""Approved retention policy with aggregate-only dry-run and idempotent execution."""

import argparse
import calendar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from partner_reports.config import AppEnvironment, get_settings
from partner_reports.pdf_imports.storage import PrivatePdfStorage, build_pdf_storage
from partner_reports.persistence.database import get_session_factory
from partner_reports.persistence.models import (
    AuditEvent,
    PdfImportBatch,
    PdfSourceDocument,
    ReportVersion,
)
from partner_reports.web.artifacts import SyntheticArtifactStore, build_artifact_store


@dataclass(frozen=True)
class RetentionPlan:
    sources: tuple[PdfSourceDocument, ...]
    reports: tuple[ReportVersion, ...]
    audit_before: datetime
    audit_count: int

    def counts(self) -> dict[str, int]:
        return {
            "source_objects": len(self.sources),
            "report_objects": len(self.reports),
            "audit_events": self.audit_count,
        }


def _months_before(value: datetime, months: int) -> datetime:
    total = value.year * 12 + value.month - 1 - months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def plan_retention(db: Session, *, now: datetime | None = None) -> RetentionPlan:
    current = now or datetime.now(UTC)
    source_cutoff = current - timedelta(days=30)
    report_cutoff = _months_before(current, 12)
    audit_cutoff = _months_before(current, 24)
    sources = tuple(
        db.scalars(
            select(PdfSourceDocument)
            .join(PdfImportBatch, PdfImportBatch.source_document_id == PdfSourceDocument.id)
            .where(
                PdfSourceDocument.purged_at.is_(None),
                PdfImportBatch.state.in_(("approved", "superseded")),
                PdfImportBatch.updated_at <= source_cutoff,
            )
            .distinct()
            .order_by(PdfSourceDocument.id)
        ).all()
    )
    reports = tuple(
        db.scalars(
            select(ReportVersion)
            .where(
                ReportVersion.purged_at.is_(None),
                ReportVersion.status == "superseded",
                ReportVersion.generated_at <= report_cutoff,
                ReportVersion.storage_object_key.is_not(None),
            )
            .order_by(ReportVersion.id)
        ).all()
    )
    audit_count = (
        db.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.occurred_at <= audit_cutoff))
        or 0
    )
    return RetentionPlan(sources, reports, audit_cutoff, audit_count)


def execute_retention(
    db: Session,
    plan: RetentionPlan,
    *,
    source_store: PrivatePdfStorage,
    report_store: SyntheticArtifactStore,
    now: datetime | None = None,
) -> dict[str, int]:
    """Remove private bytes before marking metadata; retry remains safe after interruption."""

    current = now or datetime.now(UTC)
    for source in plan.sources:
        source_store.delete(source.storage_object_key)
        source.purged_at = current
    for report in plan.reports:
        if report.storage_object_key:
            report_store.remove_generated(report.storage_object_key)
        report.purged_at = current
    db.execute(delete(AuditEvent).where(AuditEvent.occurred_at <= plan.audit_before))
    return plan.counts()


def main() -> None:
    parser = argparse.ArgumentParser(description="Aplicar retenção aprovada sem exibir dados")
    parser.add_argument("--execute", action="store_true", help="Executa; o padrão é dry-run")
    args = parser.parse_args()
    settings = get_settings()
    if settings.app_env not in (AppEnvironment.STAGING, AppEnvironment.PRODUCTION):
        parser.error("retenção operacional exige staging ou production")
    source_store = build_pdf_storage(settings.pdf_storage_root, settings.app_env)
    report_store = build_artifact_store(
        settings.report_storage_root, settings.app_env, settings.pdf_data_scope
    )
    with get_session_factory()() as db:
        plan = plan_retention(db)
        counts = plan.counts()
        if args.execute:
            execute_retention(db, plan, source_store=source_store, report_store=report_store)
            db.commit()
        print(
            "retention_mode={} source_objects={} report_objects={} audit_events={}".format(
                "execute" if args.execute else "dry-run", *counts.values()
            )
        )


if __name__ == "__main__":
    main()

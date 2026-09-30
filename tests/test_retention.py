"""Retention uses synthetic metadata and private temporary object roots."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from partner_reports.config import AppEnvironment
from partner_reports.pdf_imports.storage import PersistentPrivatePdfStorage
from partner_reports.persistence.models import (
    AuditEvent,
    Partner,
    PdfImportBatch,
    PdfSourceDocument,
    ReportVersion,
)
from partner_reports.retention import execute_retention, plan_retention
from partner_reports.web.artifacts import PersistentArtifactStore


def test_retention_dry_run_then_idempotent_removal(db_session: Session, tmp_path) -> None:
    now = datetime(2026, 9, 25, 12, tzinfo=UTC)
    source_store = PersistentPrivatePdfStorage(tmp_path / "sources", AppEnvironment.STAGING)
    report_store = PersistentArtifactStore(tmp_path / "reports", AppEnvironment.STAGING)
    source_key = "pdf-source/0123456789abcdef0123456789abcdef.pdf"
    source_store.put(source_key, b"synthetic-private-pdf")
    report_key, _ = report_store.write_generated(b"SYNTHETIC-report", b"%PDF-synthetic")

    partner = Partner(external_id="SYNTHETIC-RETENTION", name="Parceiro sintético", status="active")
    source = PdfSourceDocument(
        source_sha256="a" * 64,
        storage_object_key=source_key,
        byte_size=21,
        page_count=1,
        media_type="application/pdf",
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    db_session.add_all((partner, source))
    db_session.flush()
    batch = PdfImportBatch(
        source_document_id=source.id,
        partner_id=partner.id,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        state="superseded",
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
        updated_at=datetime(2026, 7, 2, tzinfo=UTC),
    )
    report = ReportVersion(
        partner_id=partner.id,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 1, 31),
        version=1,
        status="superseded",
        generated_at=datetime(2025, 1, 31, tzinfo=UTC),
        storage_object_key=report_key,
    )
    old_audit = AuditEvent(
        occurred_at=datetime(2024, 1, 1, tzinfo=UTC),
        action="synthetic_old_event",
        entity_type="partner",
        entity_id=partner.id,
        correlation_id=uuid.uuid4(),
        changed_fields=[],
    )
    recent_audit = AuditEvent(
        occurred_at=datetime(2026, 9, 1, tzinfo=UTC),
        action="synthetic_recent_event",
        entity_type="partner",
        entity_id=partner.id,
        correlation_id=uuid.uuid4(),
        changed_fields=[],
    )
    db_session.add_all((batch, report, old_audit, recent_audit))
    db_session.flush()

    plan = plan_retention(db_session, now=now)
    assert plan.counts() == {"source_objects": 1, "report_objects": 1, "audit_events": 1}
    assert source_store.get(source_key) == b"synthetic-private-pdf"

    execute_retention(
        db_session,
        plan,
        source_store=source_store,
        report_store=report_store,
        now=now,
    )
    db_session.flush()
    assert source.purged_at == now
    assert report.purged_at == now
    assert db_session.get(AuditEvent, old_audit.id) is None
    assert db_session.scalar(select(AuditEvent.id).where(AuditEvent.id == recent_audit.id))
    assert plan_retention(db_session, now=now).counts() == {
        "source_objects": 0,
        "report_objects": 0,
        "audit_events": 0,
    }

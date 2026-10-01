"""Idempotent job turning an approved PDF batch into the ADR-007 partner report."""

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from partner_reports.config import AppEnvironment, PdfDataScope, Settings
from partner_reports.pdf_imports.reporting import BatchReportUnavailable, load_batch_report
from partner_reports.persistence.models import (
    Partner,
    ReportGenerationRequest,
    ReportVersion,
)
from partner_reports.reports.partner_render import (
    generate_partner_report_pdf,
    render_partner_report_html,
)
from partner_reports.web.artifacts import build_artifact_store


def enqueue_approved_batch(
    db: Session,
    batch_id: uuid.UUID,
    *,
    environment: AppEnvironment,
    requested_by: uuid.UUID | None = None,
    settings: Settings | None = None,
) -> bool:
    """Queue one revision only; caller owns the transaction."""

    data = load_batch_report(db, batch_id, environment=environment, settings=settings)
    db.scalar(select(Partner.id).where(Partner.id == data.partner_id).with_for_update())
    existing = db.scalar(
        select(ReportVersion.id).where(
            ReportVersion.partner_id == data.partner_id,
            ReportVersion.pdf_batch_id == batch_id,
            ReportVersion.source_digest == data.revision_key,
        )
    )
    if existing is not None:
        return False
    active = db.scalar(
        select(ReportGenerationRequest).where(
            ReportGenerationRequest.partner_id == data.partner_id,
            ReportGenerationRequest.status.in_(("pending", "running")),
        )
    )
    if active is not None:
        if active.pdf_batch_id == batch_id and active.source_digest == data.revision_key:
            return False
        raise BatchReportUnavailable("outra geração já está ativa para o parceiro")
    db.add(
        ReportGenerationRequest(
            partner_id=data.partner_id,
            requested_by=requested_by,
            status="pending",
            pdf_batch_id=batch_id,
            source_digest=data.revision_key,
        )
    )
    db.flush()
    return True


async def process_claimed_pdf_batch(
    sessions: sessionmaker[Session],
    environment: AppEnvironment,
    output_root: Path,
    request_id: uuid.UUID,
    token: uuid.UUID,
    *,
    pdf_renderer: Callable | None = None,
    settings: Settings | None = None,
) -> str:
    """Build two artifacts before the single visible version commit."""

    from partner_reports.jobs.automation import _failure

    store = build_artifact_store(
        output_root,
        environment,
        settings.pdf_data_scope if settings is not None else PdfDataScope.SYNTHETIC_ONLY,
    )
    object_key: str | None = None
    failure_code = "SOURCE_UNAVAILABLE"
    try:
        with sessions() as db:
            request = db.get(ReportGenerationRequest, request_id)
            if request is None or request.pdf_batch_id is None:
                raise BatchReportUnavailable("solicitação sem lote")
            data = load_batch_report(
                db, request.pdf_batch_id, environment=environment, settings=settings
            )
            if request.source_digest != data.revision_key:
                failure_code = "SOURCE_CHANGED"
                raise BatchReportUnavailable("revisão alterada")
            prior = db.scalar(
                select(ReportVersion.id).where(
                    ReportVersion.partner_id == data.partner_id,
                    ReportVersion.pdf_batch_id == data.batch_id,
                    ReportVersion.source_digest == data.revision_key,
                )
            )
            if prior is not None:
                with sessions() as update_db, update_db.begin():
                    current = update_db.get(
                        ReportGenerationRequest, request_id, with_for_update=True
                    )
                    if current.status == "running" and current.lease_token == token:
                        current.status = "succeeded"
                        current.finished_at = datetime.now(UTC)
                        current.lease_token = None
                        current.lease_expires_at = None
                return "succeeded"
            next_version = (
                db.scalar(
                    select(func.coalesce(func.max(ReportVersion.version), 0)).where(
                        ReportVersion.partner_id == data.partner_id,
                        ReportVersion.period_start == data.period_start,
                        ReportVersion.period_end == data.as_of.date(),
                    )
                )
                + 1
            )
            generated_at = datetime.now(UTC)
            failure_code = "UNSAFE_REPORT"
            report = data.build_full(generated_at=generated_at, version=next_version)
            customer_count = report.indicators.clients
            case_count = report.indicators.cases
            html = render_partner_report_html(report).encode("utf-8")
        failure_code = "PDF_FAILED"
        pdf = await asyncio.wait_for(
            (pdf_renderer or generate_partner_report_pdf)(report), timeout=240
        )
        object_key, content_hash = store.write_generated(html, pdf)
        failure_code = "COMMIT_FAILED"
        with sessions() as db, db.begin():
            current = db.get(ReportGenerationRequest, request_id, with_for_update=True)
            if (
                current is None
                or current.status != "running"
                or current.lease_token != token
                or current.lease_expires_at <= datetime.now(UTC)
            ):
                failure_code = "SOURCE_CHANGED"
                raise BatchReportUnavailable("lease expirado")
            fresh = load_batch_report(
                db, current.pdf_batch_id, environment=environment, settings=settings
            )
            if fresh.revision_key != data.revision_key:
                failure_code = "SOURCE_CHANGED"
                raise BatchReportUnavailable("revisão alterada")
            db.add(
                ReportVersion(
                    partner_id=data.partner_id,
                    period_start=data.period_start,
                    period_end=data.as_of.date(),
                    version=next_version,
                    status="validated",
                    generated_at=generated_at,
                    storage_object_key=object_key,
                    content_sha256=content_hash,
                    source_digest=data.revision_key,
                    pdf_batch_id=data.batch_id,
                    customer_count=customer_count,
                    case_count=case_count,
                    partnership_percentage=report.percentage,
                )
            )
            current.status = "succeeded"
            current.finished_at = datetime.now(UTC)
            current.lease_token = None
            current.lease_expires_at = None
            current.error_code = None
        return "succeeded"
    except Exception:
        if object_key:
            store.remove_generated(object_key)
        _failure(sessions, request_id, token, failure_code)
        return "failed"

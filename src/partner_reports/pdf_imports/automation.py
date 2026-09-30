"""Durable, scoped worker for private PDF parsing and GET-only reconciliation."""

import asyncio
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from partner_reports.config import PdfDataScope, Settings
from partner_reports.integrations.advbox.client import AdvboxAuditError, AdvboxClient
from partner_reports.pdf_imports.processing import parse_quarantined_batch
from partner_reports.pdf_imports.reconciliation import collect_verified_snapshot
from partner_reports.pdf_imports.reconciliation_service import persist_scoped_reconciliation
from partner_reports.pdf_imports.storage import PrivatePdfStorage
from partner_reports.persistence.models import Partner, PdfImportBatch

_LEASE = timedelta(minutes=5)
_MAX_ATTEMPTS = 3


def _scope_clause(settings: Settings):
    if settings.pdf_data_scope is PdfDataScope.SYNTHETIC_ONLY:
        return Partner.external_id.startswith("SYNTHETIC-")
    return Partner.external_id.in_(settings.pilot_partner_ids)


def _recover_expired(db: Session, settings: Settings, now: datetime) -> None:
    rows = db.scalars(
        select(PdfImportBatch)
        .join(Partner, Partner.id == PdfImportBatch.partner_id)
        .where(
            _scope_clause(settings),
            PdfImportBatch.processing_status == "running",
            PdfImportBatch.processing_lease_expires_at < now,
        )
        .with_for_update(skip_locked=True)
    ).all()
    for batch in rows:
        batch.processing_lease_token = None
        batch.processing_lease_expires_at = None
        batch.processing_heartbeat_at = None
        batch.processing_error_code = "PROCESSING_ABANDONED"
        if batch.processing_attempt_count >= _MAX_ATTEMPTS:
            batch.processing_status = "failed"
            batch.processing_finished_at = now
        else:
            batch.processing_status = "pending"
            batch.processing_available_at = now


def claim_pdf_import(
    sessions: sessionmaker[Session], settings: Settings
) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Claim one allowlisted batch using a durable lease and row-level locking."""

    with sessions() as db, db.begin():
        now = datetime.now(UTC)
        _recover_expired(db, settings, now)
        batch = db.scalar(
            select(PdfImportBatch)
            .join(Partner, Partner.id == PdfImportBatch.partner_id)
            .where(
                _scope_clause(settings),
                Partner.status == "active",
                Partner.deleted_at.is_(None),
                PdfImportBatch.processing_status == "pending",
                (PdfImportBatch.processing_available_at.is_(None))
                | (PdfImportBatch.processing_available_at <= now),
                (PdfImportBatch.state.in_(("quarantined", "parsed")))
                | (PdfImportBatch.state == "needs_review"),
            )
            .order_by(PdfImportBatch.created_at, PdfImportBatch.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if batch is None:
            return None
        token = uuid.uuid4()
        batch.processing_status = "running"
        batch.processing_attempt_count += 1
        batch.processing_available_at = None
        batch.processing_lease_token = token
        batch.processing_lease_expires_at = now + _LEASE
        batch.processing_heartbeat_at = now
        batch.processing_finished_at = None
        batch.processing_error_code = None
        return batch.id, token


def heartbeat_pdf_import(
    sessions: sessionmaker[Session], batch_id: uuid.UUID, token: uuid.UUID
) -> bool:
    with sessions() as db, db.begin():
        batch = db.get(PdfImportBatch, batch_id, with_for_update=True)
        if (
            batch is None
            or batch.processing_status != "running"
            or batch.processing_lease_token != token
        ):
            return False
        now = datetime.now(UTC)
        batch.processing_heartbeat_at = now
        batch.processing_lease_expires_at = now + _LEASE
        return True


async def _heartbeat_loop(
    sessions: sessionmaker[Session], batch_id: uuid.UUID, token: uuid.UUID
) -> None:
    while True:
        await asyncio.sleep(30)
        if not heartbeat_pdf_import(sessions, batch_id, token):
            return


def _owns_lease(batch: PdfImportBatch | None, token: uuid.UUID) -> bool:
    return bool(
        batch is not None
        and batch.processing_status == "running"
        and batch.processing_lease_token == token
        and batch.processing_lease_expires_at is not None
        and batch.processing_lease_expires_at > datetime.now(UTC)
    )


def _finish(
    sessions: sessionmaker[Session],
    batch_id: uuid.UUID,
    token: uuid.UUID,
    *,
    status: str,
    error_code: str | None = None,
) -> None:
    with sessions() as db, db.begin():
        batch = db.get(PdfImportBatch, batch_id, with_for_update=True)
        if not _owns_lease(batch, token):
            return
        now = datetime.now(UTC)
        batch.processing_lease_token = None
        batch.processing_lease_expires_at = None
        batch.processing_heartbeat_at = None
        batch.processing_error_code = error_code
        if status == "succeeded":
            batch.processing_status = "succeeded"
            batch.processing_finished_at = now
            return
        if batch.processing_attempt_count >= _MAX_ATTEMPTS:
            batch.processing_status = "failed"
            batch.processing_finished_at = now
        else:
            batch.processing_status = "pending"
            batch.processing_available_at = now + timedelta(
                seconds=30 * 2**batch.processing_attempt_count
            )


async def process_one_pdf_import(
    sessions: sessionmaker[Session],
    settings: Settings,
    storage: PrivatePdfStorage,
    client: AdvboxClient,
) -> str:
    """Parse and reconcile one scoped batch; retries resume from the last committed boundary."""

    claimed = claim_pdf_import(sessions, settings)
    if claimed is None:
        return "empty"
    batch_id, token = claimed
    pulse = asyncio.create_task(_heartbeat_loop(sessions, batch_id, token))
    try:
        with sessions() as db, db.begin():
            batch = db.get(PdfImportBatch, batch_id, with_for_update=True)
            if not _owns_lease(batch, token):
                return "lost_lease"
            if batch.state == "quarantined":
                manifest = parse_quarantined_batch(db, storage, batch.id)
                if manifest is None:
                    terminal = batch.state == "rejected"
                    result = "rejected" if terminal else "failed"
                else:
                    result = "parsed"
            else:
                result = "parsed"
        if result in {"rejected", "failed"}:
            _finish(
                sessions,
                batch_id,
                token,
                status="succeeded" if result == "rejected" else "failed",
                error_code=None if result == "rejected" else "PDF_PROCESSING_FAILED",
            )
            return result

        snapshot = await collect_verified_snapshot(client)
        with sessions() as db, db.begin():
            batch = db.get(PdfImportBatch, batch_id, with_for_update=True)
            if not _owns_lease(batch, token):
                return "lost_lease"
            persist_scoped_reconciliation(db, batch_id, snapshot, settings=settings)
            now = datetime.now(UTC)
            batch.processing_status = "succeeded"
            batch.processing_finished_at = now
            batch.processing_lease_token = None
            batch.processing_lease_expires_at = None
            batch.processing_heartbeat_at = None
            batch.processing_error_code = None
        return "succeeded"
    except AdvboxAuditError:
        _finish(sessions, batch_id, token, status="failed", error_code="API_READ_FAILED")
        return "retry"
    except Exception:
        _finish(sessions, batch_id, token, status="failed", error_code="PROCESSING_FAILED")
        return "retry"
    finally:
        pulse.cancel()
        with suppress(asyncio.CancelledError):
            await pulse


def retry_failed_pdf_imports(sessions: sessionmaker[Session], settings: Settings) -> int:
    """Requeue terminal processing failures only inside the configured data scope."""

    with sessions() as db, db.begin():
        batches = db.scalars(
            select(PdfImportBatch)
            .join(Partner, Partner.id == PdfImportBatch.partner_id)
            .where(_scope_clause(settings), PdfImportBatch.processing_status == "failed")
            .with_for_update(skip_locked=True)
        ).all()
        for batch in batches:
            batch.processing_status = "pending"
            batch.processing_attempt_count = 0
            batch.processing_available_at = None
            batch.processing_finished_at = None
            batch.processing_error_code = None
        return len(batches)


def pdf_import_status(sessions: sessionmaker[Session], settings: Settings) -> dict[str, int]:
    """Return count-only queue status for scoped batches."""

    with sessions() as db:
        rows = db.execute(
            select(PdfImportBatch.processing_status, func.count())
            .join(Partner, Partner.id == PdfImportBatch.partner_id)
            .where(_scope_clause(settings))
            .group_by(PdfImportBatch.processing_status)
        ).all()
        return {name: count for name, count in rows}

"""Leased, restartable automation for synthetic local portfolios only.

The real Advbox sync remains an explicitly gated stage-11 operation. This module
demonstrates the orchestration contract without touching that integration.
"""

import asyncio
import hashlib
import uuid
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from partner_reports.config import AppEnvironment
from partner_reports.persistence.models import (
    Partner,
    ReportGenerationRequest,
    ReportVersion,
    SyncChangedPartner,
    SyncRun,
    SyntheticPortfolio,
)
from partner_reports.reports.preview_cli import synthetic_preview
from partner_reports.reports.render import generate_pdf, render_html, to_partner_report
from partner_reports.web.artifacts import SyntheticArtifactStore

_LEASE = timedelta(seconds=90)
_TIMEOUT = 240
_MAX_ATTEMPTS = 3
_CYCLE_LOCK = 90717009
_ZONE = ZoneInfo("America/Sao_Paulo")


def _require_local(app_env: AppEnvironment) -> None:
    if app_env not in (AppEnvironment.DEVELOPMENT, AppEnvironment.TEST):
        raise RuntimeError("Automação sintética indisponível em produção")


def _digest(source: SyntheticPortfolio) -> str:
    return hashlib.sha256(f"{source.scenario}:{source.revision}".encode()).hexdigest()


def enqueue_cycle(
    sessions: sessionmaker[Session], app_env: AppEnvironment, key: str
) -> dict[str, int | str]:
    """One DB-serialized, idempotent scan; queue only changed synthetic partners."""

    _require_local(app_env)
    if (
        not key
        or len(key) > 100
        or not all(c.isascii() and (c.isalnum() or c in "-_:.") for c in key)
    ):
        raise ValueError("Chave técnica inválida")
    with sessions() as db, db.begin():
        locked = db.scalar(select(func.pg_try_advisory_xact_lock(_CYCLE_LOCK)))
        if not locked:
            return {"status": "busy", "scanned": 0, "changed": 0, "queued": 0}
        run_key = f"synthetic:{key}"
        prior = db.scalar(select(SyncRun).where(SyncRun.idempotency_key == run_key))
        if prior:
            return {
                "status": "already_done",
                "scanned": prior.fetched_count,
                "changed": prior.updated_count,
                "queued": prior.inserted_count,
            }
        now = datetime.now(UTC)
        run = SyncRun(
            idempotency_key=run_key,
            resource_type="synthetic_portfolio",
            status="running",
            started_at=now,
            fetched_count=0,
            inserted_count=0,
            updated_count=0,
            error_count=0,
        )
        db.add(run)
        db.flush()
        sources = db.scalars(
            select(SyntheticPortfolio).order_by(SyntheticPortfolio.partner_id)
        ).all()
        for source in sources:
            # Coordinate with the portal's manual queue path on this row.
            partner = db.get(Partner, source.partner_id, with_for_update=True)
            if (
                partner is None
                or not partner.external_id.startswith("SYNTHETIC-")
                or partner.status != "active"
                or partner.deleted_at is not None
            ):
                continue
            run.fetched_count += 1
            digest = _digest(source)
            previous = db.scalar(
                select(ReportVersion)
                .where(
                    ReportVersion.partner_id == partner.id,
                    ReportVersion.status.in_(("validated", "published")),
                )
                .order_by(ReportVersion.generated_at.desc(), ReportVersion.version.desc())
                .limit(1)
            )
            if previous and previous.source_digest == digest:
                continue
            run.updated_count += 1
            db.add(SyncChangedPartner(sync_run_id=run.id, partner_id=partner.id))
            pending = db.scalar(
                select(ReportGenerationRequest.id).where(
                    ReportGenerationRequest.partner_id == partner.id,
                    ReportGenerationRequest.status.in_(("pending", "running")),
                )
            )
            if pending is None:
                db.add(
                    ReportGenerationRequest(
                        partner_id=partner.id,
                        requested_by=None,
                        status="pending",
                        source_digest=digest,
                    )
                )
                run.inserted_count += 1
        run.status = "succeeded"
        run.finished_at = datetime.now(UTC)
        return {
            "status": "succeeded",
            "scanned": run.fetched_count,
            "changed": run.updated_count,
            "queued": run.inserted_count,
        }


def scheduled_key(now: datetime | None = None) -> str:
    return f"daily-{(now or datetime.now(UTC)).astimezone(_ZONE):%Y-%m-%d}"


def _recover(db: Session, now: datetime) -> None:
    abandoned = db.scalars(
        select(ReportGenerationRequest)
        .where(
            ReportGenerationRequest.status == "running",
            ReportGenerationRequest.lease_expires_at < now,
        )
        .with_for_update(skip_locked=True)
    ).all()
    for request in abandoned:
        request.lease_token = None
        request.lease_expires_at = None
        request.error_code = "WORKER_ABANDONED"
        if request.attempt_count >= _MAX_ATTEMPTS:
            request.status = "failed"
            request.finished_at = now
        else:
            request.status = "pending"
            request.available_at = now + timedelta(seconds=30 * 2**request.attempt_count)


def claim(
    sessions: sessionmaker[Session], app_env: AppEnvironment
) -> tuple[uuid.UUID, uuid.UUID] | None:
    _require_local(app_env)
    with sessions() as db, db.begin():
        now = datetime.now(UTC)
        _recover(db, now)
        request = db.scalar(
            select(ReportGenerationRequest)
            .join(Partner, Partner.id == ReportGenerationRequest.partner_id)
            .where(
                ReportGenerationRequest.status == "pending",
                (ReportGenerationRequest.available_at.is_(None))
                | (ReportGenerationRequest.available_at <= now),
                Partner.external_id.startswith("SYNTHETIC-"),
            )
            .order_by(ReportGenerationRequest.created_at, ReportGenerationRequest.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if request is None:
            return None
        token = uuid.uuid4()
        request.status = "running"
        request.attempt_count += 1
        request.lease_token = token
        request.heartbeat_at = now
        request.lease_expires_at = now + _LEASE
        request.available_at = None
        request.error_code = None
        return request.id, token


def heartbeat(sessions: sessionmaker[Session], request_id: uuid.UUID, token: uuid.UUID) -> bool:
    with sessions() as db, db.begin():
        request = db.get(ReportGenerationRequest, request_id, with_for_update=True)
        if request is None or request.status != "running" or request.lease_token != token:
            return False
        now = datetime.now(UTC)
        request.heartbeat_at = now
        request.lease_expires_at = now + _LEASE
        return True


async def _heartbeat_loop(
    sessions: sessionmaker[Session], request_id: uuid.UUID, token: uuid.UUID
) -> None:
    while True:
        await asyncio.sleep(15)
        if not heartbeat(sessions, request_id, token):
            return


def _failure(
    sessions: sessionmaker[Session], request_id: uuid.UUID, token: uuid.UUID, code: str
) -> None:
    with sessions() as db, db.begin():
        request = db.get(ReportGenerationRequest, request_id, with_for_update=True)
        if request is None or request.status != "running" or request.lease_token != token:
            return
        now = datetime.now(UTC)
        request.lease_token = None
        request.lease_expires_at = None
        request.error_code = code
        if request.attempt_count >= _MAX_ATTEMPTS or code in {
            "SOURCE_UNAVAILABLE",
            "COUNT_REGRESSION",
            "UNSAFE_REPORT",
        }:
            request.status = "failed"
            request.finished_at = now
        else:
            request.status = "pending"
            request.available_at = now + timedelta(seconds=30 * 2**request.attempt_count)


async def process_one(
    sessions: sessionmaker[Session],
    app_env: AppEnvironment,
    output_root: Path,
    *,
    pdf_renderer: Callable | None = None,
) -> str:
    """Render outside transaction, then expose a complete pair with one DB commit."""

    _require_local(app_env)
    claimed = claim(sessions, app_env)
    if claimed is None:
        return "empty"
    request_id, token = claimed
    store = SyntheticArtifactStore(output_root, app_env)
    key: str | None = None
    failure_code = "JOB_FAILED"
    pulse = asyncio.create_task(_heartbeat_loop(sessions, request_id, token))
    try:
        with sessions() as db:
            request = db.get(ReportGenerationRequest, request_id)
            source = db.scalar(
                select(SyntheticPortfolio).where(
                    SyntheticPortfolio.partner_id == request.partner_id
                )
            )
            partner = db.get(Partner, request.partner_id)
            if (
                source is None
                or partner is None
                or not partner.external_id.startswith("SYNTHETIC-")
            ):
                failure_code = "SOURCE_UNAVAILABLE"
                raise RuntimeError
            digest = _digest(source)
            previous = db.scalar(
                select(ReportVersion)
                .where(
                    ReportVersion.partner_id == partner.id,
                    ReportVersion.status.in_(("validated", "published")),
                )
                .order_by(ReportVersion.generated_at.desc(), ReportVersion.version.desc())
                .limit(1)
            )
            as_of = datetime.now(UTC) - timedelta(minutes=1)
            period_start = as_of.date().replace(day=1)
            next_version = (
                db.scalar(
                    select(func.coalesce(func.max(ReportVersion.version), 0)).where(
                        ReportVersion.partner_id == partner.id,
                        ReportVersion.period_start == period_start,
                        ReportVersion.period_end == as_of.date(),
                    )
                )
                + 1
            )
            internal = synthetic_preview(
                source.scenario,
                partner_id=partner.id,
                partner_code=partner.external_id,
                as_of=as_of,
                report_version=next_version,
            )
            report = to_partner_report(internal)
            customers = report.metrics.unique_customers.value
            cases = report.metrics.lawsuits.value
            if previous and (
                (previous.customer_count is not None and customers < previous.customer_count)
                or (previous.case_count is not None and cases < previous.case_count)
            ):
                failure_code = "COUNT_REGRESSION"
                raise RuntimeError
            html = render_html(internal).encode("utf-8")
        failure_code = "PDF_FAILED"
        pdf = await asyncio.wait_for((pdf_renderer or generate_pdf)(internal), timeout=_TIMEOUT)
        key, content_hash = store.write_generated(html, pdf)
        failure_code = "COMMIT_FAILED"
        with sessions() as db, db.begin():
            request = db.get(ReportGenerationRequest, request_id, with_for_update=True)
            source = db.scalar(
                select(SyntheticPortfolio).where(
                    SyntheticPortfolio.partner_id == request.partner_id
                )
            )
            if (
                request.status != "running"
                or request.lease_token != token
                or request.lease_expires_at <= datetime.now(UTC)
                or source is None
                or _digest(source) != digest
            ):
                failure_code = "SOURCE_CHANGED"
                raise RuntimeError
            db.add(
                ReportVersion(
                    partner_id=request.partner_id,
                    period_start=period_start,
                    period_end=as_of.date(),
                    version=next_version,
                    status="validated",
                    generated_at=as_of + timedelta(minutes=1),
                    storage_object_key=key,
                    content_sha256=content_hash,
                    source_digest=digest,
                    customer_count=customers,
                    case_count=cases,
                )
            )
            request.status = "succeeded"
            request.source_digest = digest
            request.finished_at = datetime.now(UTC)
            request.lease_token = None
            request.lease_expires_at = None
            request.error_code = None
        return "succeeded"
    except Exception:
        if key:
            store.remove_generated(key)
        _failure(sessions, request_id, token, failure_code)
        return "failed"
    finally:
        pulse.cancel()
        with suppress(asyncio.CancelledError):
            await pulse


def retry_failed(sessions: sessionmaker[Session], app_env: AppEnvironment) -> int:
    _require_local(app_env)
    with sessions() as db, db.begin():
        rows = db.scalars(
            select(ReportGenerationRequest)
            .join(Partner, Partner.id == ReportGenerationRequest.partner_id)
            .where(
                ReportGenerationRequest.status == "failed",
                Partner.external_id.startswith("SYNTHETIC-"),
            )
            .with_for_update(skip_locked=True)
        ).all()
        seen: set[uuid.UUID] = set()
        retried = 0
        for request in rows:
            if request.partner_id in seen:
                continue
            seen.add(request.partner_id)
            active = db.scalar(
                select(ReportGenerationRequest.id).where(
                    ReportGenerationRequest.partner_id == request.partner_id,
                    ReportGenerationRequest.status.in_(("pending", "running")),
                )
            )
            if active is not None:
                continue
            request.status = "pending"
            request.attempt_count = 0
            request.available_at = None
            request.error_code = None
            request.finished_at = None
            retried += 1
        return retried


def status(sessions: sessionmaker[Session], app_env: AppEnvironment) -> dict[str, int]:
    _require_local(app_env)
    with sessions() as db:
        counts = db.execute(
            select(ReportGenerationRequest.status, func.count())
            .join(Partner, Partner.id == ReportGenerationRequest.partner_id)
            .where(Partner.external_id.startswith("SYNTHETIC-"))
            .group_by(ReportGenerationRequest.status)
        ).all()
        return {name: count for name, count in counts}


def bump_revision(
    sessions: sessionmaker[Session], app_env: AppEnvironment, partner_code: str
) -> int:
    _require_local(app_env)
    if not partner_code.startswith("SYNTHETIC-"):
        raise ValueError("Apenas parceiro sintético")
    with sessions() as db, db.begin():
        source = db.scalar(
            select(SyntheticPortfolio)
            .join(Partner, Partner.id == SyntheticPortfolio.partner_id)
            .where(Partner.external_id == partner_code)
            .with_for_update()
        )
        if source is None:
            raise ValueError("Fonte sintética não encontrada")
        source.revision += 1
        return source.revision

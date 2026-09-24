"""Stage-9 orchestration tests use synthetic sources and fake PDF bytes."""

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from partner_reports.config import AppEnvironment, get_settings
from partner_reports.jobs.automation import (
    claim,
    enqueue_cycle,
    heartbeat,
    process_one,
    retry_failed,
    scheduled_key,
)
from partner_reports.persistence.models import (
    Partner,
    ReportGenerationRequest,
    ReportVersion,
    SyntheticPortfolio,
)
from partner_reports.web.artifacts import SyntheticArtifactStore

pytestmark = pytest.mark.database


@pytest.fixture
def setup(db_session: Session, tmp_path: Path):
    partner = Partner(external_id=f"SYNTHETIC-AUTO-{uuid.uuid4().hex}", name="Carteira sintética")
    db_session.add(partner)
    db_session.flush()
    db_session.add(SyntheticPortfolio(partner_id=partner.id, scenario="one", revision=1))
    db_session.flush()
    sessions = sessionmaker(
        bind=db_session.get_bind(), expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    return sessions, partner.id, tmp_path


async def _pdf(_internal):
    return b"%PDF-1.4\nsynthetic test only"


def _versions(db: Session, partner_id: uuid.UUID) -> list[ReportVersion]:
    return db.scalars(select(ReportVersion).where(ReportVersion.partner_id == partner_id)).all()


def test_cycle_idempotent_and_incremental(setup, db_session):
    sessions, partner_id, tmp_path = setup
    first = enqueue_cycle(sessions, AppEnvironment.TEST, f"test-{uuid.uuid4().hex}")
    assert first["queued"] >= 1
    assert (
        asyncio.run(process_one(sessions, AppEnvironment.TEST, tmp_path, pdf_renderer=_pdf))
        == "succeeded"
    )
    assert len(_versions(db_session, partner_id)) == 1
    repeated = enqueue_cycle(sessions, AppEnvironment.TEST, f"test-{uuid.uuid4().hex}")
    assert repeated["queued"] == 0
    source = db_session.scalar(
        select(SyntheticPortfolio).where(SyntheticPortfolio.partner_id == partner_id)
    )
    source.revision += 1
    db_session.flush()
    changed = enqueue_cycle(sessions, AppEnvironment.TEST, f"test-{uuid.uuid4().hex}")
    assert changed["queued"] == 1


def test_pdf_failure_keeps_previous_version_and_retry(setup, db_session):
    sessions, partner_id, tmp_path = setup
    previous = ReportVersion(
        partner_id=partner_id,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 16),
        version=1,
        status="validated",
        generated_at=datetime(2026, 9, 16, 12, tzinfo=UTC),
        storage_object_key="synthetic/one",
        customer_count=1,
        case_count=1,
    )
    db_session.add(previous)
    db_session.add(ReportGenerationRequest(partner_id=partner_id, status="pending"))
    db_session.flush()

    async def broken(_internal):
        raise RuntimeError("never persist this exception")

    assert (
        asyncio.run(process_one(sessions, AppEnvironment.TEST, tmp_path, pdf_renderer=broken))
        == "failed"
    )
    assert [v.id for v in _versions(db_session, partner_id)] == [previous.id]
    request = db_session.scalar(
        select(ReportGenerationRequest).where(ReportGenerationRequest.partner_id == partner_id)
    )
    assert request.error_code == "PDF_FAILED"
    assert request.status == "pending"
    request.available_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()
    assert (
        asyncio.run(process_one(sessions, AppEnvironment.TEST, tmp_path, pdf_renderer=_pdf))
        == "succeeded"
    )
    versions = _versions(db_session, partner_id)
    assert len(versions) == 2
    assert previous.status == "validated"
    generated = next(v for v in versions if v.id != previous.id)
    store = SyntheticArtifactStore(tmp_path, AppEnvironment.TEST)
    assert store.read(generated.storage_object_key, "pdf").startswith(b"%PDF")
    assert b"SYNTHETIC-" in store.read(generated.storage_object_key, "html")


def test_abandoned_lease_recovered_and_stale_token_fenced(setup, db_session):
    sessions, partner_id, tmp_path = setup
    db_session.add(ReportGenerationRequest(partner_id=partner_id, status="pending"))
    db_session.flush()
    first = claim(sessions, AppEnvironment.TEST)
    assert first is not None
    request = db_session.get(ReportGenerationRequest, first[0])
    request.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()
    assert claim(sessions, AppEnvironment.TEST) is None  # backoff after abandonment
    assert not heartbeat(sessions, first[0], first[1])
    request.available_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()
    second = claim(sessions, AppEnvironment.TEST)
    assert second is not None and second[1] != first[1]
    assert not heartbeat(sessions, first[0], first[1])
    assert heartbeat(sessions, second[0], second[1])


def test_source_change_during_pdf_cannot_publish(setup, db_session):
    sessions, partner_id, tmp_path = setup
    db_session.add(ReportGenerationRequest(partner_id=partner_id, status="pending"))
    db_session.flush()

    async def mutate_while_rendering(_internal):
        source = db_session.scalar(
            select(SyntheticPortfolio).where(SyntheticPortfolio.partner_id == partner_id)
        )
        source.revision += 1
        db_session.flush()
        return await _pdf(_internal)

    assert (
        asyncio.run(
            process_one(
                sessions, AppEnvironment.TEST, tmp_path, pdf_renderer=mutate_while_rendering
            )
        )
        == "failed"
    )
    assert _versions(db_session, partner_id) == []
    assert list((tmp_path / "pdf").glob("generated_*.pdf")) == []
    request = db_session.scalar(
        select(ReportGenerationRequest).where(ReportGenerationRequest.partner_id == partner_id)
    )
    assert request.error_code == "SOURCE_CHANGED"


def test_count_regression_blocks_new_version(setup, db_session):
    sessions, partner_id, tmp_path = setup
    db_session.add(
        ReportVersion(
            partner_id=partner_id,
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 16),
            version=1,
            status="validated",
            generated_at=datetime(2026, 9, 16, 12, tzinfo=UTC),
            customer_count=30,
            case_count=55,
        )
    )
    db_session.add(ReportGenerationRequest(partner_id=partner_id, status="pending"))
    db_session.flush()
    assert (
        asyncio.run(process_one(sessions, AppEnvironment.TEST, tmp_path, pdf_renderer=_pdf))
        == "failed"
    )
    assert len(_versions(db_session, partner_id)) == 1
    request = db_session.scalar(
        select(ReportGenerationRequest).where(ReportGenerationRequest.partner_id == partner_id)
    )
    assert request.status == "failed" and request.error_code == "COUNT_REGRESSION"


def test_cycle_mutex_and_failed_only_retry(setup, db_session):
    sessions, partner_id, _ = setup
    engine = create_engine(get_settings().database_url.get_secret_value())
    try:
        with engine.begin() as connection:
            assert connection.scalar(select(func.pg_try_advisory_xact_lock(90717009)))
            assert (
                enqueue_cycle(sessions, AppEnvironment.TEST, f"busy-{uuid.uuid4().hex}")["status"]
                == "busy"
            )
    finally:
        engine.dispose()
    key = f"test-{uuid.uuid4().hex}"
    assert enqueue_cycle(sessions, AppEnvironment.TEST, key)["status"] == "succeeded"
    assert enqueue_cycle(sessions, AppEnvironment.TEST, key)["status"] == "already_done"
    request = db_session.scalar(
        select(ReportGenerationRequest).where(ReportGenerationRequest.partner_id == partner_id)
    )
    request.status = "failed"
    request.attempt_count = 3
    db_session.flush()
    assert retry_failed(sessions, AppEnvironment.TEST) >= 1
    db_session.expire(request)
    assert request.status == "pending" and request.attempt_count == 0


def test_production_is_closed(setup):
    sessions, _, tmp_path = setup
    with pytest.raises(RuntimeError):
        enqueue_cycle(sessions, AppEnvironment.PRODUCTION, "forbidden")
    with pytest.raises(RuntimeError):
        asyncio.run(process_one(sessions, AppEnvironment.PRODUCTION, tmp_path, pdf_renderer=_pdf))
    assert scheduled_key(datetime(2026, 9, 17, 2, tzinfo=UTC)) == "daily-2026-09-16"

"""PDF-6: approved synthetic batch to a private, reproducible report version."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from partner_reports.config import AppEnvironment
from partner_reports.jobs.automation import process_one
from partner_reports.jobs.pdf_batch_reports import enqueue_approved_batch
from partner_reports.pdf_imports.reconciliation import ApiCandidate, ApiSnapshot, _snapshot_digest
from partner_reports.pdf_imports.reconciliation_service import persist_synthetic_reconciliation
from partner_reports.pdf_imports.reporting import BatchReportUnavailable, load_batch_report
from partner_reports.pdf_imports.review_service import approve_batch
from partner_reports.persistence.models import (
    AppUser,
    Customer,
    FinancialTransaction,
    Lawsuit,
    LawsuitCustomer,
    Movement,
    Partner,
    PdfImportBatch,
    PdfManifestItem,
    PdfSourceDocument,
    ReportGenerationRequest,
    ReportVersion,
)
from partner_reports.web.artifacts import SyntheticArtifactStore

pytestmark = pytest.mark.database


def _approved_batch(db: Session) -> PdfImportBatch:
    token = "".join("abcdefghijklmnop"[int(digit, 16)] for digit in uuid.uuid4().hex)
    today = datetime.now(UTC).date()
    partner = Partner(external_id=f"SYNTHETIC-PDF-SIX-{token}", name="Carteira sintética")
    customer = Customer(advbox_id=9_200_001, name="Nome sintético " + "longo " * 30)
    lawsuit = Lawsuit(
        advbox_id=9_200_002,
        process_number="1234567-89.2026.1.23.4567",
        folder="SYNTHETIC-FOLDER",
        status="active",
    )
    reviewer = AppUser(external_subject=f"local:pdf6-{token}", status="active")
    db.add_all((partner, customer, lawsuit, reviewer))
    db.flush()
    db.add(LawsuitCustomer(lawsuit_id=lawsuit.id, customer_id=customer.id))
    db.add(
        Movement(
            lawsuit_id=lawsuit.id,
            source_fingerprint=uuid.uuid4().hex * 2,
            occurred_at=datetime.now(UTC) - timedelta(days=1),
            title="Andamento sintético extenso " * 40,
        )
    )
    db.add_all(
        FinancialTransaction(
            advbox_id=9_200_003 + index,
            lawsuit_id=lawsuit.id,
            amount_status="available",
            amount=0,
            entry_type="credit",
            category="Categoria sintética restrita " * 5,
            is_internal=index % 2 == 0,
        )
        for index in range(25)
    )
    source = PdfSourceDocument(
        source_sha256=uuid.uuid4().hex * 2,
        storage_object_key=f"pdf-source/{uuid.uuid4().hex}.pdf",
        byte_size=1000,
        page_count=1,
        media_type="application/pdf",
    )
    db.add(source)
    db.flush()
    batch = PdfImportBatch(
        source_document_id=source.id,
        partner_id=partner.id,
        period_start=today.replace(day=1),
        period_end=today,
        parser_version="advbox-manifest-1",
        layout_version="advbox-positional-1",
        parsed_item_count=1,
        parse_quality_count=0,
        state="parsed",
    )
    db.add(batch)
    db.flush()
    db.add(
        PdfManifestItem(
            batch_id=batch.id,
            source_ordinal=1,
            process_number_normalized="12345678920261234567",
            folder_exact="SYNTHETIC-FOLDER",
            source_page_start=1,
            source_page_end=1,
            quality_flags=[],
        )
    )
    db.flush()
    candidate = ApiCandidate(
        lawsuit.advbox_id,
        "12345678920261234567",
        "SYNTHETIC-FOLDER",
        "synthetic-hash",
    )
    snapshot = ApiSnapshot(_snapshot_digest((candidate,)), 1, datetime.now(UTC), (candidate,))
    persist_synthetic_reconciliation(db, batch.id, snapshot, environment=AppEnvironment.TEST)
    approve_batch(
        db,
        batch.id,
        batch.review_revision,
        reviewer.id,
        environment=AppEnvironment.TEST,
        four_eyes=False,
    )
    return batch


async def _fake_pdf(_internal):
    return b"%PDF-1.4\nsynthetic only"


def test_approved_batch_generates_one_private_version_and_keeps_prior_on_failure(
    db_session: Session, tmp_path: Path
) -> None:
    batch = _approved_batch(db_session)
    sessions = sessionmaker(
        bind=db_session.get_bind(), expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    data = load_batch_report(db_session, batch.id, environment=AppEnvironment.TEST)
    assert data.snapshot.source_complete
    assert len(data.snapshot.cases) == 1
    assert len(data.snapshot.customers) == 1
    assert enqueue_approved_batch(db_session, batch.id, environment=AppEnvironment.TEST)
    assert not enqueue_approved_batch(db_session, batch.id, environment=AppEnvironment.TEST)
    assert (
        asyncio.run(process_one(sessions, AppEnvironment.TEST, tmp_path, pdf_renderer=_fake_pdf))
        == "succeeded"
    )
    versions = db_session.scalars(
        select(ReportVersion).where(ReportVersion.partner_id == batch.partner_id)
    ).all()
    assert len(versions) == 1
    version = versions[0]
    assert version.pdf_batch_id == batch.id
    assert version.source_digest == data.revision_key
    assert version.customer_count == 1 and version.case_count == 1
    store = SyntheticArtifactStore(tmp_path, AppEnvironment.TEST)
    html = store.read(version.storage_object_key, "html").decode()
    assert "1 casos" in html
    assert "Nome sintético" not in html
    assert "Andamento sintético" not in html
    assert "Categoria sintética" not in html
    assert not enqueue_approved_batch(db_session, batch.id, environment=AppEnvironment.TEST)
    version.status = "superseded"
    db_session.flush()
    assert not enqueue_approved_batch(db_session, batch.id, environment=AppEnvironment.TEST)
    version.status = "validated"
    db_session.flush()
    source = db_session.get(PdfSourceDocument, batch.source_document_id)
    source.source_sha256 = uuid.uuid4().hex * 2
    db_session.flush()
    assert enqueue_approved_batch(db_session, batch.id, environment=AppEnvironment.TEST)

    async def broken(_internal):
        raise RuntimeError("synthetic PDF failure")

    assert (
        asyncio.run(process_one(sessions, AppEnvironment.TEST, tmp_path, pdf_renderer=broken))
        == "failed"
    )
    assert (
        db_session.scalar(
            select(ReportGenerationRequest.error_code).where(
                ReportGenerationRequest.pdf_batch_id == batch.id,
                ReportGenerationRequest.status == "pending",
            )
        )
        == "PDF_FAILED"
    )
    assert (
        len(
            db_session.scalars(
                select(ReportVersion).where(ReportVersion.partner_id == batch.partner_id)
            ).all()
        )
        == 1
    )
    assert store.read(version.storage_object_key, "pdf").startswith(b"%PDF")


def test_batch_report_supports_production_like_synthetic_validation_and_rejects_unapproved(
    db_session: Session,
) -> None:
    batch = _approved_batch(db_session)
    report = load_batch_report(db_session, batch.id, environment=AppEnvironment.PRODUCTION)
    assert report.batch_id == batch.id
    batch.state = "superseded"
    db_session.flush()
    with pytest.raises(BatchReportUnavailable):
        enqueue_approved_batch(db_session, batch.id, environment=AppEnvironment.TEST)


def test_changed_batch_revision_after_render_removes_partial_artifacts(
    db_session: Session, tmp_path: Path
) -> None:
    batch = _approved_batch(db_session)
    sessions = sessionmaker(
        bind=db_session.get_bind(), expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    enqueue_approved_batch(db_session, batch.id, environment=AppEnvironment.TEST)

    async def mutate_during_pdf(_internal):
        source = db_session.get(PdfSourceDocument, batch.source_document_id)
        source.source_sha256 = uuid.uuid4().hex * 2
        db_session.flush()
        return await _fake_pdf(_internal)

    assert (
        asyncio.run(
            process_one(sessions, AppEnvironment.TEST, tmp_path, pdf_renderer=mutate_during_pdf)
        )
        == "failed"
    )
    assert (
        db_session.scalars(
            select(ReportVersion).where(ReportVersion.partner_id == batch.partner_id)
        ).all()
        == []
    )
    assert list((tmp_path / "pdf").glob("generated_*.pdf")) == []
    request = db_session.scalar(
        select(ReportGenerationRequest).where(ReportGenerationRequest.pdf_batch_id == batch.id)
    )
    assert request.error_code == "SOURCE_CHANGED"


@pytest.mark.browser
def test_approved_batch_generates_real_a4_pdf_without_restricted_fields(
    db_session: Session, tmp_path: Path
) -> None:
    batch = _approved_batch(db_session)
    sessions = sessionmaker(
        bind=db_session.get_bind(), expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    enqueue_approved_batch(db_session, batch.id, environment=AppEnvironment.TEST)
    assert asyncio.run(process_one(sessions, AppEnvironment.TEST, tmp_path)) == "succeeded"
    version = db_session.scalar(select(ReportVersion).where(ReportVersion.pdf_batch_id == batch.id))
    path = tmp_path / "pdf" / f"generated_{version.storage_object_key.rsplit('/', 1)[1]}.pdf"
    reader = PdfReader(path)
    assert len(reader.pages) == 1
    page = reader.pages[0]
    assert round(float(page.mediabox.width)) == 595
    assert round(float(page.mediabox.height)) == 842
    text = page.extract_text() or ""
    assert "SYNTHETIC-PDF-SIX" in text
    assert "Nome sintético" not in text
    assert "Andamento sintético" not in text
    assert "Categoria sintética" not in text

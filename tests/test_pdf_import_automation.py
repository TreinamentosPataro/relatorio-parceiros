"""Durable PDF processing tests use only synthetic documents and API responses."""

import asyncio
import io
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from partner_reports.config import AppEnvironment, Settings
from partner_reports.integrations.advbox.client import AdvboxClient
from partner_reports.integrations.advbox.config import AdvboxAuditSettings
from partner_reports.jobs.automation import process_one
from partner_reports.jobs.pdf_batch_reports import enqueue_approved_batch
from partner_reports.pdf_imports.automation import process_one_pdf_import
from partner_reports.pdf_imports.review_service import approve_batch
from partner_reports.pdf_imports.service import receive_pdf
from partner_reports.pdf_imports.storage import LocalPrivatePdfStorage
from partner_reports.pdf_imports.validation import validate_pdf
from partner_reports.persistence.models import (
    AppUser,
    Customer,
    Lawsuit,
    LawsuitCustomer,
    Partner,
    PdfImportBatch,
    PdfManifestItem,
    PdfReconciliationItem,
    PdfReconciliationRun,
    ReportGenerationRequest,
    ReportVersion,
)
from partner_reports.web.artifacts import build_artifact_store

pytestmark = pytest.mark.database


def _manifest_pdf() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=595.28, height=841.89)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(
        b"\n".join(
            (
                b"BT /F1 10 Tf 2 700 Td (Relatorio) Tj ET",
                b"BT /F1 10 Tf 2 123 Td (Processo 1234567-89.2026.1.23.4567) Tj ET",
                b"BT /F1 10 Tf 93 179 Td (Pasta) Tj ET",
                b"BT /F1 10 Tf 136 179 Td (PASTA-01) Tj ET",
            )
        )
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="postgresql+psycopg://synthetic:synthetic@db/synthetic",
        pdf_data_scope="private_pilot",
        _env_file=None,
    )


def _api_settings() -> AdvboxAuditSettings:
    return AdvboxAuditSettings(
        advbox_api_token=SecretStr("synthetic-token"),
        advbox_audit_max_retries=0,
        _env_file=None,
    )


def _create_batch(
    db: Session,
    storage: LocalPrivatePdfStorage,
    *,
    external_id: str,
    digest_variant: bytes = b"",
    pilot_enabled: bool = True,
) -> PdfImportBatch:
    partner = Partner(
        external_id=external_id,
        name=f"Parceiro técnico {external_id}",
        pilot_enabled=pilot_enabled,
    )
    uploader = AppUser(external_subject=f"local:{external_id.lower()}", status="active")
    db.add_all([partner, uploader])
    db.flush()
    content = _manifest_pdf() + digest_variant
    result = receive_pdf(
        db,
        storage,
        validate_pdf(content),
        partner_id=partner.id,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        uploaded_by=uploader.id,
    )
    db.flush()
    return result.batch


def _sessions(db: Session) -> sessionmaker[Session]:
    return sessionmaker(
        bind=db.get_bind(), expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


def _success_handler(calls: list[str]):
    rows = [
        {
            "id": 9_000_401,
            "process_number": "1234567-89.2026.1.23.4567",
            "protocol_number": "RESTRICTED-NOT-PERSISTED",
            "folder": "PASTA-01",
            "group_id": 101,
            "stages_id": 202,
            "responsible_id": 303,
            "customers": [{"customer_id": 8_000_101, "name": "RESTRICTED-NOT-PERSISTED"}],
        },
        {
            "id": 9_000_499,
            "process_number": "7654321-98.2026.1.23.4567",
            "folder": "OUTRA-PASTA",
            "customers": [{"customer_id": 8_000_199}],
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(
            200,
            json={"data": rows, "totalCount": 2, "limit": 100, "offset": 0},
        )

    return handler


def test_worker_processes_only_pilot_enabled_batch(db_session: Session, tmp_path) -> None:
    storage = LocalPrivatePdfStorage(tmp_path / "pdf", AppEnvironment.TEST)
    allowed = _create_batch(db_session, storage, external_id="PILOT-001")
    blocked = _create_batch(
        db_session,
        storage,
        external_id="PILOT-002",
        digest_variant=b"\n% synthetic variant",
        pilot_enabled=False,
    )
    calls: list[str] = []

    async def execute() -> str:
        client = AdvboxClient(
            _api_settings(), transport=httpx.MockTransport(_success_handler(calls))
        )
        try:
            return await process_one_pdf_import(_sessions(db_session), _settings(), storage, client)
        finally:
            await client.aclose()

    assert asyncio.run(execute()) == "succeeded"
    db_session.expire_all()
    assert db_session.get(PdfImportBatch, allowed.id).state == "needs_review"
    assert db_session.get(PdfImportBatch, allowed.id).processing_status == "succeeded"
    assert db_session.get(PdfImportBatch, blocked.id).state == "quarantined"
    assert db_session.get(PdfImportBatch, blocked.id).processing_status == "pending"
    assert calls == ["GET", "GET"]
    lawsuit = db_session.scalar(select(Lawsuit).where(Lawsuit.advbox_id == 9_000_401))
    assert lawsuit is not None
    assert lawsuit.process_number == "12345678920261234567"
    assert lawsuit.folder == "PASTA-01"
    assert lawsuit.protocol_number is None
    assert lawsuit.group_id is None
    assert lawsuit.stage_id is None
    assert lawsuit.responsible_id is None
    assert db_session.scalar(select(Lawsuit.id).where(Lawsuit.advbox_id == 9_000_499)) is None
    customer = db_session.scalar(select(Customer).where(Customer.advbox_id == 8_000_101))
    assert customer is not None and customer.name is None
    assert db_session.scalar(select(Customer.id).where(Customer.advbox_id == 8_000_199)) is None
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(LawsuitCustomer)
            .where(
                LawsuitCustomer.lawsuit_id == lawsuit.id,
                LawsuitCustomer.customer_id == customer.id,
            )
        )
        == 1
    )
    proposal = db_session.scalar(
        select(PdfReconciliationItem)
        .join(PdfReconciliationRun)
        .where(PdfReconciliationRun.batch_id == allowed.id)
    )
    assert proposal.matched_lawsuit_id == lawsuit.id
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PdfReconciliationRun)
            .where(PdfReconciliationRun.batch_id == allowed.id)
        )
        == 1
    )


def test_worker_resumes_from_parsed_boundary_after_api_failure(
    db_session: Session, tmp_path
) -> None:
    storage = LocalPrivatePdfStorage(tmp_path / "pdf", AppEnvironment.TEST)
    batch = _create_batch(db_session, storage, external_id="PILOT-001")

    async def first_attempt() -> str:
        client = AdvboxClient(
            _api_settings(), transport=httpx.MockTransport(lambda _: httpx.Response(503))
        )
        try:
            return await process_one_pdf_import(_sessions(db_session), _settings(), storage, client)
        finally:
            await client.aclose()

    assert asyncio.run(first_attempt()) == "retry"
    db_session.expire_all()
    row = db_session.get(PdfImportBatch, batch.id)
    assert row.state == "parsed"
    assert row.processing_status == "pending"
    assert row.processing_error_code == "API_READ_FAILED"
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PdfManifestItem)
            .where(PdfManifestItem.batch_id == batch.id)
        )
        == 1
    )
    row.processing_available_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()
    calls: list[str] = []

    async def second_attempt() -> str:
        client = AdvboxClient(
            _api_settings(), transport=httpx.MockTransport(_success_handler(calls))
        )
        try:
            return await process_one_pdf_import(_sessions(db_session), _settings(), storage, client)
        finally:
            await client.aclose()

    assert asyncio.run(second_attempt()) == "succeeded"
    db_session.expire_all()
    row = db_session.get(PdfImportBatch, batch.id)
    assert row.state == "needs_review"
    assert row.processing_status == "succeeded"
    assert row.processing_attempt_count == 2
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PdfManifestItem)
            .where(PdfManifestItem.batch_id == batch.id)
        )
        == 1
    )
    assert calls == ["GET", "GET"]


def test_private_pilot_review_links_and_minimized_report(db_session: Session, tmp_path) -> None:
    settings = _settings()
    storage = LocalPrivatePdfStorage(tmp_path / "pdf", AppEnvironment.TEST)
    batch = _create_batch(db_session, storage, external_id="PILOT-001")
    reviewer = AppUser(external_subject=f"local:review-{uuid.uuid4().hex}", status="active")
    db_session.add(reviewer)
    db_session.flush()

    async def process_import() -> str:
        client = AdvboxClient(_api_settings(), transport=httpx.MockTransport(_success_handler([])))
        try:
            return await process_one_pdf_import(_sessions(db_session), settings, storage, client)
        finally:
            await client.aclose()

    assert asyncio.run(process_import()) == "succeeded"
    db_session.expire_all()
    batch = db_session.get(PdfImportBatch, batch.id)
    approve_batch(
        db_session,
        batch.id,
        batch.review_revision,
        reviewer.id,
        environment=AppEnvironment.TEST,
        four_eyes=False,
        settings=settings,
    )
    assert batch.state == "approved"
    assert enqueue_approved_batch(
        db_session,
        batch.id,
        environment=AppEnvironment.TEST,
        requested_by=reviewer.id,
        settings=settings,
    )
    db_session.flush()

    async def fake_pdf(_):
        return b"%PDF-1.7\n% synthetic minimized report"

    reports = tmp_path / "reports"
    assert (
        asyncio.run(
            process_one(
                _sessions(db_session),
                AppEnvironment.TEST,
                reports,
                pdf_renderer=fake_pdf,
                settings=settings,
            )
        )
        == "succeeded"
    )
    db_session.expire_all()
    request = db_session.scalar(
        select(ReportGenerationRequest).where(ReportGenerationRequest.pdf_batch_id == batch.id)
    )
    version = db_session.scalar(select(ReportVersion).where(ReportVersion.pdf_batch_id == batch.id))
    assert request.status == "succeeded"
    assert version.status == "validated"
    assert version.customer_count == 1
    assert version.case_count == 1
    assert version.storage_object_key.startswith("private/generated/")
    store = build_artifact_store(reports, AppEnvironment.TEST, settings.pdf_data_scope)
    html = store.read(version.storage_object_key, "html")
    pdf = store.read(version.storage_object_key, "pdf")
    assert pdf.startswith(b"%PDF")
    assert b"RESTRICTED-NOT-PERSISTED" not in html
    assert b"12345678920261234567" not in html
    assert b"PASTA-01" not in html

"""Synthetic database proof that PDF-3 stores proposals without activating links."""

import asyncio
import uuid
from datetime import UTC, date, datetime

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from partner_reports.config import AppEnvironment
from partner_reports.integrations.advbox.client import AdvboxClient
from partner_reports.integrations.advbox.config import AdvboxAuditSettings
from partner_reports.pdf_imports.reconciliation import ApiCandidate, ApiSnapshot, _snapshot_digest
from partner_reports.pdf_imports.reconciliation_service import (
    dry_run_batch,
    persist_synthetic_reconciliation,
)
from partner_reports.persistence.models import (
    Lawsuit,
    Partner,
    PartnerCaseLink,
    PdfImportBatch,
    PdfManifestItem,
    PdfReconciliationItem,
    PdfReconciliationRun,
    PdfSourceDocument,
)

pytestmark = pytest.mark.database


def _setup(
    db: Session, *, partner_external_id: str = "SYNTHETIC-PDF3"
) -> tuple[uuid.UUID, uuid.UUID]:
    partner = Partner(external_id=partner_external_id, name="Synthetic Partner", status="active")
    lawsuit = Lawsuit(
        advbox_id=9_000_401,
        process_number="1234567-89.2026.1.23.4567",
        folder="PASTA-01",
        status="active",
    )
    source = PdfSourceDocument(
        source_sha256="a" * 64,
        storage_object_key=f"pdf-source/{uuid.uuid4().hex}.pdf",
        byte_size=1000,
        page_count=1,
        media_type="application/pdf",
    )
    db.add_all([partner, lawsuit, source])
    db.flush()
    batch = PdfImportBatch(
        source_document_id=source.id,
        partner_id=partner.id,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
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
            folder_exact="PASTA-01",
            source_page_start=1,
            source_page_end=1,
            quality_flags=[],
        )
    )
    db.flush()
    return batch.id, lawsuit.id


def _snapshot(folder: str = "PASTA-01") -> ApiSnapshot:
    rows = (ApiCandidate(9_000_401, "12345678920261234567", folder, "synthetic-record-digest"),)
    return ApiSnapshot(_snapshot_digest(rows), 1, datetime.now(UTC), rows)


def test_synthetic_proposal_is_idempotent_and_never_activates_link(db_session: Session) -> None:
    batch_id, lawsuit_id = _setup(db_session)
    snapshot = _snapshot()
    first = persist_synthetic_reconciliation(
        db_session, batch_id, snapshot, environment=AppEnvironment.TEST
    )
    assert first.result_total == first.matched_count == 1
    assert db_session.get(PdfImportBatch, batch_id).state == "needs_review"
    proposal = db_session.scalar(
        select(PdfReconciliationItem).where(PdfReconciliationItem.run_id == first.id)
    )
    assert proposal.status == "matched"
    assert proposal.matched_lawsuit_id == lawsuit_id
    assert proposal.method == "process_number_exact"
    assert len(proposal.evidence_sha256) == 64
    assert proposal.proposed_valid_from == date(2026, 9, 1)
    assert db_session.scalar(select(func.count()).select_from(PartnerCaseLink)) == 0

    repeated = persist_synthetic_reconciliation(
        db_session, batch_id, snapshot, environment=AppEnvironment.TEST
    )
    assert repeated.id == first.id
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PdfReconciliationRun)
            .where(PdfReconciliationRun.batch_id == batch_id)
        )
        == 1
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PdfReconciliationItem)
            .join(PdfReconciliationRun)
            .where(PdfReconciliationRun.batch_id == batch_id)
        )
        == 1
    )

    changed = persist_synthetic_reconciliation(
        db_session, batch_id, _snapshot("OTHER"), environment=AppEnvironment.TEST
    )
    assert changed.id != first.id
    assert changed.ambiguous_count == 1
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PdfReconciliationRun)
            .where(PdfReconciliationRun.batch_id == batch_id)
        )
        == 2
    )
    assert db_session.scalar(select(func.count()).select_from(PartnerCaseLink)) == 0


def test_production_like_validation_accepts_only_synthetic_partner(db_session: Session) -> None:
    batch_id, _ = _setup(db_session, partner_external_id="REAL-TECHNICAL-ID")
    with pytest.raises(ValueError, match="parceiro sintético"):
        persist_synthetic_reconciliation(
            db_session, batch_id, _snapshot(), environment=AppEnvironment.TEST
        )
    with pytest.raises(ValueError, match="parceiro sintético"):
        persist_synthetic_reconciliation(
            db_session, batch_id, _snapshot(), environment=AppEnvironment.PRODUCTION
        )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PdfReconciliationRun)
            .where(PdfReconciliationRun.batch_id == batch_id)
        )
        == 0
    )

    db_session.get(
        Partner, db_session.get(PdfImportBatch, batch_id).partner_id
    ).external_id = "SYNTHETIC-PRODUCTION-VALIDATION"
    run = persist_synthetic_reconciliation(
        db_session, batch_id, _snapshot(), environment=AppEnvironment.PRODUCTION
    )
    assert run.result_total == 1


def test_dry_run_returns_counts_without_writing(db_session: Session) -> None:
    batch_id, _ = _setup(db_session)
    row = {
        "id": 9_000_401,
        "process_number": "1234567-89.2026.1.23.4567",
        "folder": "PASTA-01",
        "customers": [],
    }
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(200, json={"data": [row], "totalCount": 1, "limit": 100, "offset": 0})

    async def execute():
        settings = AdvboxAuditSettings(advbox_api_token=SecretStr("synthetic-token"))
        client = AdvboxClient(settings, transport=httpx.MockTransport(handler))
        try:
            return await dry_run_batch(db_session, client, batch_id)
        finally:
            await client.aclose()

    summary = asyncio.run(execute())
    assert summary.total == summary.matched == 1
    assert calls == ["GET", "GET"]
    assert db_session.get(PdfImportBatch, batch_id).state == "parsed"
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PdfReconciliationRun)
            .where(PdfReconciliationRun.batch_id == batch_id)
        )
        == 0
    )

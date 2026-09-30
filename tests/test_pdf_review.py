"""PDF-4 review is synthetic, transactional and separate from publication."""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from partner_reports.config import AppEnvironment
from partner_reports.pdf_imports.reconciliation import ApiCandidate, ApiSnapshot, _snapshot_digest
from partner_reports.pdf_imports.reconciliation_service import persist_synthetic_reconciliation
from partner_reports.pdf_imports.review_service import (
    ReviewConflict,
    approve_batch,
    correct_item,
    reject_batch,
    request_reprocessing,
)
from partner_reports.persistence.models import (
    AppUser,
    Lawsuit,
    Partner,
    PartnerCaseLink,
    PdfImportBatch,
    PdfImportReview,
    PdfManifestItem,
    PdfSourceDocument,
    ReportVersion,
)

pytestmark = pytest.mark.database


def _batch(
    db: Session, partner: Partner | None = None, *, folder: str = "FOLDER-1"
) -> tuple[PdfImportBatch, Lawsuit]:
    if partner is None:
        partner = Partner(
            external_id=f"SYNTHETIC-REVIEW-{uuid.uuid4().hex}", name="Synthetic review"
        )
        db.add(partner)
    lawsuit = db.scalar(select(Lawsuit).where(Lawsuit.advbox_id == 9_000_501))
    if lawsuit is None:
        lawsuit = Lawsuit(
            advbox_id=9_000_501,
            process_number="1234567-89.2026.1.23.4567",
            folder="FOLDER-1",
            status="active",
        )
        db.add(lawsuit)
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
            folder_exact=folder,
            source_page_start=1,
            source_page_end=1,
            quality_flags=[],
        )
    )
    db.flush()
    return batch, lawsuit


def _reconcile(
    db: Session,
    batch: PdfImportBatch,
    *,
    folder: str = "FOLDER-1",
    source_digest: str = "synthetic-digest",
) -> None:
    candidates = (ApiCandidate(9_000_501, "12345678920261234567", folder, source_digest),)
    snapshot = ApiSnapshot(_snapshot_digest(candidates), 1, datetime.now(UTC), candidates)
    persist_synthetic_reconciliation(db, batch.id, snapshot, environment=AppEnvironment.TEST)


def test_approval_needs_four_eyes_and_current_revision(db_session: Session) -> None:
    db = db_session
    batch, lawsuit = _batch(db)
    uploader, reviewer = uuid.uuid4(), uuid.uuid4()
    # Real FK users are needed for decisions; use the project user model.
    from partner_reports.persistence.models import AppUser

    users = [
        AppUser(external_subject=f"local:review-{value}", status="active")
        for value in (uploader, reviewer)
    ]
    db.add_all(users)
    db.flush()
    batch.uploaded_by = users[0].id
    _reconcile(db, batch)
    with pytest.raises(ReviewConflict, match="Outro administrador"):
        approve_batch(
            db,
            batch.id,
            batch.review_revision,
            users[0].id,
            environment=AppEnvironment.TEST,
            four_eyes=True,
        )
    revision = batch.review_revision
    approve_batch(
        db, batch.id, revision, users[1].id, environment=AppEnvironment.TEST, four_eyes=True
    )
    assert batch.state == "approved"
    link = db.scalar(select(PartnerCaseLink).where(PartnerCaseLink.pdf_batch_id == batch.id))
    assert link.status == "active" and link.lawsuit_id == lawsuit.id
    assert link.reviewed_by == users[1].id
    assert (
        db.scalar(
            select(func.count())
            .select_from(ReportVersion)
            .where(ReportVersion.partner_id == batch.partner_id)
        )
        == 0
    )
    with pytest.raises(ReviewConflict, match="modificado"):
        reject_batch(db, batch.id, revision, users[0].id, environment=AppEnvironment.TEST)
    assert (
        db.scalar(
            select(func.count())
            .select_from(PdfImportReview)
            .where(PdfImportReview.batch_id == batch.id)
        )
        == 1
    )


def test_ambiguity_requires_catalogued_correction_and_flag(db_session: Session) -> None:
    db = db_session
    batch, lawsuit = _batch(db, folder="WRONG")
    from partner_reports.persistence.models import AppUser

    user = AppUser(external_subject=f"local:review-{uuid.uuid4()}", status="active")
    db.add(user)
    db.flush()
    _reconcile(db, batch)
    with pytest.raises(ReviewConflict, match="Ambiguidade"):
        approve_batch(
            db,
            batch.id,
            batch.review_revision,
            user.id,
            environment=AppEnvironment.TEST,
            four_eyes=True,
        )
    from partner_reports.persistence.models import PdfReconciliationItem, PdfReconciliationRun

    run = db.scalar(select(PdfReconciliationRun).where(PdfReconciliationRun.batch_id == batch.id))
    item = db.scalar(select(PdfReconciliationItem).where(PdfReconciliationItem.run_id == run.id))
    with pytest.raises(ReviewConflict, match="Exceções"):
        correct_item(
            db,
            batch.id,
            item.id,
            lawsuit.advbox_id,
            batch.review_revision,
            user.id,
            environment=AppEnvironment.TEST,
            enabled=False,
        )
    correct_item(
        db,
        batch.id,
        item.id,
        lawsuit.advbox_id,
        batch.review_revision,
        user.id,
        environment=AppEnvironment.TEST,
        enabled=True,
    )
    with pytest.raises(ReviewConflict, match="Exceções"):
        approve_batch(
            db,
            batch.id,
            batch.review_revision,
            user.id,
            environment=AppEnvironment.TEST,
            four_eyes=True,
        )
    approve_batch(
        db,
        batch.id,
        batch.review_revision,
        user.id,
        environment=AppEnvironment.TEST,
        four_eyes=True,
        allow_corrections=True,
    )
    link = db.scalar(select(PartnerCaseLink).where(PartnerCaseLink.pdf_batch_id == batch.id))
    assert link.match_method == "manual_existing_id"
    correction = db.scalar(
        select(PdfImportReview).where(
            PdfImportReview.decision == "corrected", PdfImportReview.batch_id == batch.id
        )
    )
    assert (
        correction.after_advbox_id == lawsuit.advbox_id
        and correction.reconciliation_item_id == item.id
    )


def test_reprocessing_and_atomic_supersession(db_session: Session) -> None:
    db = db_session
    from partner_reports.persistence.models import AppUser

    user = AppUser(external_subject=f"local:review-{uuid.uuid4()}", status="active")
    db.add(user)
    db.flush()
    old, _ = _batch(db)
    _reconcile(db, old)
    approve_batch(
        db, old.id, old.review_revision, user.id, environment=AppEnvironment.TEST, four_eyes=True
    )
    new, _ = _batch(db, db.get(Partner, old.partner_id))
    _reconcile(db, new)
    request_reprocessing(db, new.id, new.review_revision, user.id, environment=AppEnvironment.TEST)
    with pytest.raises(ReviewConflict, match="já solicitado"):
        request_reprocessing(
            db, new.id, new.review_revision, user.id, environment=AppEnvironment.TEST
        )
    with pytest.raises(ReviewConflict, match="pendente"):
        approve_batch(
            db,
            new.id,
            new.review_revision,
            user.id,
            environment=AppEnvironment.TEST,
            four_eyes=True,
        )
    _reconcile(db, new, source_digest="synthetic-digest-2")
    with pytest.raises(ReviewConflict, match="Já existe"):
        approve_batch(
            db,
            new.id,
            new.review_revision,
            user.id,
            environment=AppEnvironment.TEST,
            four_eyes=True,
        )
    approve_batch(
        db,
        new.id,
        new.review_revision,
        user.id,
        environment=AppEnvironment.TEST,
        four_eyes=True,
        replace_batch_id=old.id,
    )
    assert old.state == "superseded" and old.superseded_by_batch_id == new.id
    assert (
        db.scalar(select(PartnerCaseLink).where(PartnerCaseLink.pdf_batch_id == old.id)).status
        == "inactive"
    )
    assert (
        db.scalar(select(PartnerCaseLink).where(PartnerCaseLink.pdf_batch_id == new.id)).status
        == "active"
    )


def test_production_like_review_accepts_only_synthetic_partner(db_session: Session) -> None:
    db = db_session
    reviewer = AppUser(
        external_subject=f"local:production-validation-{uuid.uuid4().hex}", status="active"
    )
    db.add(reviewer)
    db.flush()
    batch, _ = _batch(db)
    _reconcile(db, batch)
    review = approve_batch(
        db,
        batch.id,
        batch.review_revision,
        reviewer.id,
        environment=AppEnvironment.PRODUCTION,
        four_eyes=False,
    )
    assert review.decision == "approved"

    real_batch, _ = _batch(db)
    _reconcile(db, real_batch)
    db.get(Partner, real_batch.partner_id).external_id = f"REAL-{uuid.uuid4().hex}"
    with pytest.raises(ReviewConflict, match="sintéticos"):
        approve_batch(
            db,
            real_batch.id,
            real_batch.review_revision,
            reviewer.id,
            environment=AppEnvironment.PRODUCTION,
            four_eyes=False,
        )

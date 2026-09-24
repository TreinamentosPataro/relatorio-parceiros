"""Transactional metadata creation around one already validated private PDF."""

import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from partner_reports.pdf_imports.lifecycle import PdfBatchState, require_transition
from partner_reports.pdf_imports.storage import PdfStorageUnavailable, PrivatePdfStorage
from partner_reports.pdf_imports.validation import ValidatedPdf
from partner_reports.persistence.models import PdfImportBatch, PdfImportEvent, PdfSourceDocument


@dataclass(frozen=True)
class ReceiveResult:
    batch: PdfImportBatch
    object_key: str | None
    duplicate: bool


def find_duplicate(db: Session, digest: str) -> PdfImportBatch | None:
    return db.scalar(
        select(PdfImportBatch)
        .join(PdfSourceDocument, PdfSourceDocument.id == PdfImportBatch.source_document_id)
        .where(PdfSourceDocument.source_sha256 == digest)
    )


def receive_pdf(
    db: Session,
    storage: PrivatePdfStorage,
    validated: ValidatedPdf,
    *,
    partner_id: uuid.UUID,
    period_start: date,
    period_end: date,
    uploaded_by: uuid.UUID,
) -> ReceiveResult:
    """Store one object and stage its metadata; the caller owns commit/rollback cleanup."""

    duplicate = find_duplicate(db, validated.source_sha256)
    if duplicate is not None:
        return ReceiveResult(batch=duplicate, object_key=None, duplicate=True)

    source_id = uuid.uuid4()
    object_key = f"pdf-source/{source_id.hex}.pdf"
    storage.put(object_key, validated.content)
    try:
        source = PdfSourceDocument(
            id=source_id,
            source_sha256=validated.source_sha256,
            storage_object_key=object_key,
            byte_size=validated.byte_size,
            page_count=validated.page_count,
            media_type="application/pdf",
        )
        batch = PdfImportBatch(
            source_document_id=source.id,
            partner_id=partner_id,
            period_start=period_start,
            period_end=period_end,
            parser_version=None,
            layout_version=None,
            state=PdfBatchState.QUARANTINED,
            uploaded_by=uploaded_by,
        )
        require_transition(PdfBatchState.UPLOADED, PdfBatchState.QUARANTINED)
        db.add(source)
        db.flush()
        db.add(batch)
        db.flush()
        db.add_all(
            [
                PdfImportEvent(
                    batch_id=batch.id,
                    actor_user_id=uploaded_by,
                    from_state=None,
                    to_state=PdfBatchState.UPLOADED,
                ),
                PdfImportEvent(
                    batch_id=batch.id,
                    actor_user_id=uploaded_by,
                    from_state=PdfBatchState.UPLOADED,
                    to_state=PdfBatchState.QUARANTINED,
                ),
            ]
        )
        db.flush()
    except Exception:
        with suppress(PdfStorageUnavailable):
            storage.delete(object_key)
        raise
    return ReceiveResult(batch=batch, object_key=object_key, duplicate=False)

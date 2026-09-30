"""Transactional persistence boundary for the versioned manifest parser."""

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from partner_reports.pdf_imports.lifecycle import PdfBatchState, require_transition
from partner_reports.pdf_imports.parser import PARSER_VERSION, ParsedManifest, parse_pdf_manifest
from partner_reports.pdf_imports.storage import PdfStorageUnavailable, PrivatePdfStorage
from partner_reports.pdf_imports.validation import PdfRejected
from partner_reports.persistence.models import (
    PdfImportBatch,
    PdfImportEvent,
    PdfManifestItem,
    PdfSourceDocument,
)


def _transition(
    db: Session, batch: PdfImportBatch, target: PdfBatchState, code: str | None = None
) -> None:
    previous = PdfBatchState(batch.state)
    require_transition(previous, target)
    batch.state = target
    db.add(
        PdfImportEvent(batch_id=batch.id, from_state=previous, to_state=target, reason_code=code)
    )


def parse_quarantined_batch(
    db: Session, storage: PrivatePdfStorage, batch_id: uuid.UUID
) -> ParsedManifest | None:
    """Parse one quarantined batch. Caller commits; no source text reaches persistence."""
    batch = db.get(PdfImportBatch, batch_id, with_for_update=True)
    if batch is None or batch.state != PdfBatchState.QUARANTINED:
        raise ValueError("lote indisponível para parse")
    source = db.get(PdfSourceDocument, batch.source_document_id)
    if source is None:
        raise ValueError("fonte indisponível")

    _transition(db, batch, PdfBatchState.PARSING)
    batch.parser_version = PARSER_VERSION
    try:
        content = storage.get(source.storage_object_key)
        if hashlib.sha256(content).hexdigest() != source.source_sha256:
            raise PdfRejected("PDF_MALFORMED")
        manifest = parse_pdf_manifest(content)
        if manifest.page_count != source.page_count:
            raise PdfRejected("PDF_MALFORMED")
    except PdfRejected as exc:
        _transition(db, batch, PdfBatchState.REJECTED, exc.code)
        batch.rejection_code = exc.code
        return None
    except PdfStorageUnavailable:
        _transition(db, batch, PdfBatchState.FAILED, "PDF_STORAGE_UNAVAILABLE")
        return None

    batch.layout_version = manifest.layout_version
    batch.parsed_item_count = len(manifest.items)
    batch.parse_quality_count = sum(bool(item.quality_flags) for item in manifest.items)
    batch.parsed_at = datetime.now(UTC)
    for item in manifest.items:
        db.add(
            PdfManifestItem(
                id=item.manifest_item_id,
                batch_id=batch.id,
                source_ordinal=item.source_ordinal,
                process_number_normalized=item.process_number_normalized,
                folder_exact=item.folder_exact,
                source_page_start=item.source_page_start,
                source_page_end=item.source_page_end,
                quality_flags=list(item.quality_flags),
            )
        )
    needs_review = not manifest.items or any(
        set(item.quality_flags) - {"page_continuation"} for item in manifest.items
    )
    _transition(db, batch, PdfBatchState.NEEDS_REVIEW if needs_review else PdfBatchState.PARSED)
    db.flush()
    return manifest

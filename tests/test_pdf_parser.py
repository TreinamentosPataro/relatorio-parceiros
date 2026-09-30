"""Synthetic structural fixtures for PDF-2; no reference PDF content is copied."""

import hashlib
import io
import uuid

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from partner_reports.pdf_imports.parser import LAYOUT_VERSION, PARSER_VERSION, parse_pdf_manifest
from partner_reports.pdf_imports.processing import parse_quarantined_batch
from partner_reports.pdf_imports.storage import PdfStorageUnavailable
from partner_reports.pdf_imports.validation import PdfRejected
from partner_reports.persistence.models import (
    PdfImportBatch,
    PdfImportEvent,
    PdfManifestItem,
    PdfSourceDocument,
)


def fixture_pdf(
    *,
    pages: int = 1,
    items: tuple[tuple[str, str], ...] = (),
    empty: bool = False,
    heading: str = "Relatorio",
    scan_page: int | None = None,
    annotation: bool = False,
) -> bytes:
    writer = PdfWriter()
    for page_index in range(pages):
        page = writer.add_blank_page(width=595.28, height=841.89)
        if scan_page == page_index:
            continue
        commands = [f"BT /F1 10 Tf 2 700 Td ({heading}) Tj ET"]
        if empty and page_index == 0:
            commands.append("BT /F1 10 Tf 2 660 Td (Nenhum processo) Tj ET")
        if page_index == 0:
            for ordinal, (number, folder) in enumerate(items):
                offset = ordinal * 250
                commands.extend(
                    [
                        f"BT /F1 10 Tf 2 {123 + offset} Td (Processo {number}) Tj ET",
                        f"BT /F1 10 Tf 93 {179 + offset} Td (Pasta) Tj ET",
                        f"BT /F1 10 Tf 136 {179 + offset} Td ({folder}) Tj ET",
                        "BT /F1 10 Tf 100 300 Td (Contato: texto sintetico descartado) Tj ET",
                    ]
                )
        else:
            commands.append("BT /F1 10 Tf 100 300 Td (Continuacao sintetica) Tj ET")
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
        stream.set_data("\n".join(commands).encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    if annotation:
        from pypdf.generic import ArrayObject, FloatObject

        writer.add_annotation(
            page_number=0,
            annotation=DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Annot"),
                    NameObject("/Subtype"): NameObject("/Highlight"),
                    NameObject("/Rect"): ArrayObject([FloatObject(1)] * 4),
                }
            ),
        )
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_zero_and_one_item_are_deterministic_and_minimal() -> None:
    empty = parse_pdf_manifest(fixture_pdf(empty=True))
    assert empty.items == ()
    assert empty.quality_flags == ("zero_processes",)
    content = fixture_pdf(items=(("1234567-89.2026.1.23.4567", "PASTA-01"),))
    first = parse_pdf_manifest(content)
    assert first == parse_pdf_manifest(content)
    assert first.parser_version == PARSER_VERSION
    assert first.layout_version == LAYOUT_VERSION
    assert first.items[0].process_number_normalized == "12345678920261234567"
    assert first.items[0].folder_exact == "PASTA-01"
    assert "Contato" not in repr(first)


def test_55_pages_continuation_and_many_items() -> None:
    content = fixture_pdf(pages=55, items=(("", "PASTA-01"),))
    result = parse_pdf_manifest(content)
    assert len(result.items) == 1
    assert (result.items[0].source_page_start, result.items[0].source_page_end) == (1, 55)
    assert "page_continuation" in result.items[0].quality_flags
    many = parse_pdf_manifest(fixture_pdf(items=tuple(("", f"PASTA-{n:02d}") for n in range(8))))
    assert len(many.items) == 8
    assert [item.source_ordinal for item in many.items] == list(range(1, 9))


def test_missing_number_duplicate_and_missing_identifier_need_review() -> None:
    result = parse_pdf_manifest(fixture_pdf(items=(("", "PASTA-01"), ("", "PASTA-01"), ("", ""))))
    assert result.items[0].process_number_normalized is None
    assert "duplicate_source" in result.items[1].quality_flags
    assert "missing_identifier" in result.items[2].quality_flags


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"heading": "Outro documento", "items": (("", "PASTA-01"),)}, "LAYOUT_UNKNOWN"),
        ({"scan_page": 0}, "TEXT_LAYER_REQUIRED"),
        ({"pages": 2, "scan_page": 1, "items": (("", "PASTA-01"),)}, "TEXT_LAYER_REQUIRED"),
        ({"annotation": True, "items": (("", "PASTA-01"),)}, "PDF_ANNOTATED_SOURCE"),
    ],
)
def test_unrecognized_scan_and_annotated_sources_fail_closed(kwargs: dict, code: str) -> None:
    with pytest.raises(PdfRejected) as raised:
        parse_pdf_manifest(fixture_pdf(**kwargs))
    assert raised.value.code == code


class _MemorySession:
    def __init__(self, batch: PdfImportBatch, source: PdfSourceDocument):
        self.batch = batch
        self.source = source
        self.added: list[object] = []

    def get(self, model, identity, **kwargs):
        return self.batch if model is PdfImportBatch else self.source

    def add(self, value):
        self.added.append(value)

    def flush(self):
        pass


class _MemoryStorage:
    def __init__(self, content: bytes):
        self.content = content

    def get(self, key: str) -> bytes:
        return self.content


def _batch_for(content: bytes) -> tuple[_MemorySession, uuid.UUID]:
    batch_id = uuid.uuid4()
    source_id = uuid.uuid4()
    batch = PdfImportBatch(id=batch_id, source_document_id=source_id, state="quarantined")
    source = PdfSourceDocument(
        id=source_id,
        source_sha256=hashlib.sha256(content).hexdigest(),
        page_count=1,
        storage_object_key="pdf-source/0123456789abcdef0123456789abcdef.pdf",
    )
    return _MemorySession(batch, source), batch_id


def test_persistence_boundary_stores_only_manifest_and_counts() -> None:
    content = fixture_pdf(items=(("1234567-89.2026.1.23.4567", "PASTA-01"),))
    db, batch_id = _batch_for(content)
    manifest = parse_quarantined_batch(db, _MemoryStorage(content), batch_id)
    assert manifest is not None
    assert db.batch.state == "parsed"
    assert db.batch.parsed_item_count == 1
    assert db.batch.parse_quality_count == 0
    stored = [value for value in db.added if isinstance(value, PdfManifestItem)]
    assert len(stored) == 1
    assert stored[0].folder_exact == "PASTA-01"
    assert "Contato" not in repr(stored[0])
    assert [event.to_state for event in db.added if isinstance(event, PdfImportEvent)] == [
        "parsing",
        "parsed",
    ]


def test_persistence_boundary_rejects_changed_source_and_storage_failure() -> None:
    content = fixture_pdf(items=(("", "PASTA-01"),))
    db, batch_id = _batch_for(content)
    assert parse_quarantined_batch(db, _MemoryStorage(b"changed"), batch_id) is None
    assert db.batch.state == "rejected"
    assert db.batch.rejection_code == "PDF_MALFORMED"
    assert not any(isinstance(value, PdfManifestItem) for value in db.added)

    class FailingStorage:
        def get(self, key: str) -> bytes:
            raise PdfStorageUnavailable("storage indisponível")

    db, batch_id = _batch_for(content)
    assert parse_quarantined_batch(db, FailingStorage(), batch_id) is None
    assert db.batch.state == "failed"


def test_parser_complexity_limit_is_catalogued(monkeypatch) -> None:
    import partner_reports.pdf_imports.parser as parser

    monkeypatch.setattr(parser, "_MAX_CHARS_PER_PAGE", 10)
    with pytest.raises(PdfRejected) as raised:
        parser.parse_pdf_manifest(fixture_pdf(items=(("", "PASTA-01"),)))
    assert raised.value.code == "PARSER_LIMIT_EXCEEDED"


@pytest.mark.database
def test_synthetic_upload_parse_reconcile_review_approve_without_publication(
    db_session, tmp_path
) -> None:
    from datetime import UTC, date, datetime

    from sqlalchemy import func, select

    from partner_reports.config import AppEnvironment
    from partner_reports.pdf_imports.reconciliation import (
        ApiCandidate,
        ApiSnapshot,
        _snapshot_digest,
    )
    from partner_reports.pdf_imports.reconciliation_service import persist_synthetic_reconciliation
    from partner_reports.pdf_imports.review_service import approve_batch
    from partner_reports.pdf_imports.service import receive_pdf
    from partner_reports.pdf_imports.storage import LocalPrivatePdfStorage
    from partner_reports.pdf_imports.validation import validate_pdf
    from partner_reports.persistence.models import (
        AppUser,
        Lawsuit,
        Partner,
        PartnerCaseLink,
        PdfImportReview,
        ReportVersion,
    )

    db = db_session
    partner = Partner(external_id=f"SYNTHETIC-FULL-{uuid.uuid4().hex}", name="Synthetic")
    uploader = AppUser(external_subject=f"local:upload-{uuid.uuid4().hex}", status="active")
    reviewer = AppUser(external_subject=f"local:review-{uuid.uuid4().hex}", status="active")
    lawsuit = Lawsuit(
        advbox_id=9_000_777,
        process_number="1234567-89.2026.1.23.4567",
        folder="PASTA-01",
        status="active",
    )
    db.add_all([partner, uploader, reviewer, lawsuit])
    db.flush()
    content = fixture_pdf(pages=2, items=(("1234567-89.2026.1.23.4567", "PASTA-01"),))
    storage = LocalPrivatePdfStorage(tmp_path / "pdf", AppEnvironment.TEST)
    received = receive_pdf(
        db,
        storage,
        validate_pdf(content),
        partner_id=partner.id,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        uploaded_by=uploader.id,
    )
    batch = received.batch
    assert batch.state == "quarantined"
    manifest = parse_quarantined_batch(db, storage, batch.id)
    assert manifest is not None and batch.state == "parsed"
    assert batch.parse_quality_count == 1  # Continuation is permitted after review.
    candidates = (ApiCandidate(9_000_777, "12345678920261234567", "PASTA-01", "synthetic-digest"),)
    snapshot = ApiSnapshot(_snapshot_digest(candidates), 1, datetime.now(UTC), candidates)
    persist_synthetic_reconciliation(db, batch.id, snapshot, environment=AppEnvironment.TEST)
    assert batch.state == "needs_review"
    approve_batch(
        db,
        batch.id,
        batch.review_revision,
        reviewer.id,
        environment=AppEnvironment.TEST,
        four_eyes=True,
    )
    assert batch.state == "approved"
    assert (
        db.scalar(
            select(func.count())
            .select_from(PdfImportEvent)
            .where(PdfImportEvent.batch_id == batch.id)
        )
        == 7
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(PdfImportReview)
            .where(PdfImportReview.batch_id == batch.id)
        )
        == 1
    )
    link = db.scalar(select(PartnerCaseLink).where(PartnerCaseLink.pdf_batch_id == batch.id))
    assert link.status == "active" and link.reviewed_by == reviewer.id
    assert (
        db.scalar(
            select(func.count())
            .select_from(ReportVersion)
            .where(ReportVersion.partner_id == partner.id)
        )
        == 0
    )

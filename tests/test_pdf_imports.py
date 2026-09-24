"""Synthetic-only tests for the private PDF-1 ingestion boundary."""

import io

import pytest
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject

from partner_reports.config import AppEnvironment
from partner_reports.pdf_imports.lifecycle import PdfBatchState, require_transition
from partner_reports.pdf_imports.storage import LocalPrivatePdfStorage, PdfStorageUnavailable
from partner_reports.pdf_imports.validation import (
    MAX_PDF_BYTES,
    MAX_PDF_PAGES,
    PdfRejected,
    validate_pdf,
    validate_upload_metadata,
)


def synthetic_pdf(*, pages: int = 1, annotation_subtype: str | None = None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595.28, height=841.89)
    if annotation_subtype:
        writer.add_annotation(
            page_number=0,
            annotation=DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Annot"),
                    NameObject("/Subtype"): NameObject(annotation_subtype),
                    NameObject("/Rect"): ArrayObject(
                        [FloatObject(10), FloatObject(10), FloatObject(20), FloatObject(20)]
                    ),
                }
            ),
        )
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_valid_pdf_is_inspected_without_text_extraction() -> None:
    content = synthetic_pdf(annotation_subtype="/Link")
    result = validate_pdf(content)
    assert result.page_count == 1
    assert result.byte_size == len(content)
    assert result.link_annotation_count == 1
    assert len(result.source_sha256) == 64


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"", "FILE_EMPTY"),
        (b"not-a-pdf", "FILE_NOT_PDF"),
        (b"%PDF-broken", "PDF_MALFORMED"),
    ],
)
def test_invalid_or_oversized_pdf_is_rejected(content: bytes, code: str) -> None:
    with pytest.raises(PdfRejected, match=code):
        validate_pdf(content)


def test_oversized_pdf_is_rejected() -> None:
    with pytest.raises(PdfRejected, match="SIZE_LIMIT_EXCEEDED"):
        validate_pdf(b"%PDF-" + b"x" * MAX_PDF_BYTES)


def test_annotated_pdf_is_rejected_but_link_is_classified() -> None:
    with pytest.raises(PdfRejected, match="PDF_ANNOTATED_SOURCE"):
        validate_pdf(synthetic_pdf(annotation_subtype="/Highlight"))
    assert validate_pdf(synthetic_pdf(annotation_subtype="/Link")).link_annotation_count == 1


def test_page_count_and_format_limits() -> None:
    with pytest.raises(PdfRejected, match="PAGE_LIMIT_EXCEEDED"):
        validate_pdf(synthetic_pdf(pages=MAX_PDF_PAGES + 1))
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(PdfRejected, match="PAGE_FORMAT_UNSUPPORTED"):
        validate_pdf(output.getvalue())


def test_metadata_rejects_spoofed_or_unsafe_filename() -> None:
    validate_upload_metadata("exportacao.pdf", "application/pdf")
    for filename, media_type in (
        ("exportacao.txt", "application/pdf"),
        ("../exportacao.pdf", "application/pdf"),
        ("exportacao.pdf", "text/plain"),
    ):
        with pytest.raises(PdfRejected, match="FILE_NOT_PDF"):
            validate_upload_metadata(filename, media_type)


def test_local_storage_is_atomic_private_and_refused_in_production(tmp_path) -> None:
    key = "pdf-source/0123456789abcdef0123456789abcdef.pdf"
    storage = LocalPrivatePdfStorage(tmp_path, AppEnvironment.TEST)
    storage.put(key, b"synthetic")
    assert (tmp_path / key).read_bytes() == b"synthetic"
    storage.delete(key)
    assert not (tmp_path / key).exists()
    production = LocalPrivatePdfStorage(tmp_path, AppEnvironment.PRODUCTION)
    with pytest.raises(PdfStorageUnavailable):
        production.put(key, b"synthetic")


def test_lifecycle_accepts_only_contract_transitions() -> None:
    require_transition(PdfBatchState.UPLOADED, PdfBatchState.QUARANTINED)
    require_transition(PdfBatchState.FAILED, PdfBatchState.QUARANTINED)
    require_transition(PdfBatchState.APPROVED, PdfBatchState.SUPERSEDED)
    with pytest.raises(ValueError, match="transição"):
        require_transition(PdfBatchState.UPLOADED, PdfBatchState.APPROVED)
    with pytest.raises(ValueError, match="transição"):
        require_transition(PdfBatchState.REJECTED, PdfBatchState.QUARANTINED)

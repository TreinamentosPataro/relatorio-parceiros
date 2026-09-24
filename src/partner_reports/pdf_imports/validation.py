"""Bounded structural validation that never extracts PDF text."""

import hashlib
import io
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 200
_A4_WIDTH = 595.28
_A4_HEIGHT = 841.89
_PAGE_TOLERANCE = 5.0
_ALLOWED_ANNOTATION = "/Link"


class PdfRejected(ValueError):
    """A catalogued rejection with no source content or filename in its message."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ValidatedPdf:
    content: bytes
    source_sha256: str
    byte_size: int
    page_count: int
    link_annotation_count: int


def validate_upload_metadata(filename: str | None, media_type: str | None) -> None:
    """Validate and immediately discard client-controlled filename semantics."""

    if (
        not filename
        or len(filename) > 255
        or "/" in filename
        or "\\" in filename
        or any(ord(character) < 32 for character in filename)
        or not filename.lower().endswith(".pdf")
        or media_type != "application/pdf"
    ):
        raise PdfRejected("FILE_NOT_PDF")


def validate_pdf(content: bytes) -> ValidatedPdf:
    """Inspect PDF objects and page geometry without calling text extraction."""

    size = len(content)
    if size == 0:
        raise PdfRejected("FILE_EMPTY")
    if size > MAX_PDF_BYTES:
        raise PdfRejected("SIZE_LIMIT_EXCEEDED")
    if not content.startswith(b"%PDF-"):
        raise PdfRejected("FILE_NOT_PDF")
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise PdfRejected("PDF_ENCRYPTED")
        page_count = len(reader.pages)
        if page_count == 0:
            raise PdfRejected("PDF_MALFORMED")
        if page_count > MAX_PDF_PAGES:
            raise PdfRejected("PAGE_LIMIT_EXCEEDED")

        root = reader.trailer.get("/Root")
        if root is None:
            raise PdfRejected("PDF_MALFORMED")
        root_object = root.get_object()
        if root_object.get("/AcroForm") is not None:
            raise PdfRejected("PDF_ANNOTATED_SOURCE")
        names = root_object.get("/Names")
        if names is not None and names.get_object().get("/EmbeddedFiles") is not None:
            raise PdfRejected("PDF_ANNOTATED_SOURCE")

        link_count = 0
        for page in reader.pages:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            if (
                abs(width - _A4_WIDTH) > _PAGE_TOLERANCE
                or abs(height - _A4_HEIGHT) > _PAGE_TOLERANCE
            ):
                raise PdfRejected("PAGE_FORMAT_UNSUPPORTED")
            annotations = page.get("/Annots") or []
            for reference in annotations:
                annotation = reference.get_object()
                if annotation.get("/Subtype") != _ALLOWED_ANNOTATION:
                    raise PdfRejected("PDF_ANNOTATED_SOURCE")
                link_count += 1
    except PdfRejected:
        raise
    except (PdfReadError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise PdfRejected("PDF_MALFORMED") from exc

    return ValidatedPdf(
        content=content,
        source_sha256=hashlib.sha256(content).hexdigest(),
        byte_size=size,
        page_count=page_count,
        link_annotation_count=link_count,
    )

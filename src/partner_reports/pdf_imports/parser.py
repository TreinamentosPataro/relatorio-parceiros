"""Versioned, bounded extraction of an allowlisted Advbox PDF manifest."""

import io
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from partner_reports.pdf_imports.identifiers import normalize_process_number
from partner_reports.pdf_imports.validation import PdfRejected, validate_pdf

PARSER_VERSION = "advbox-manifest-1"
LAYOUT_VERSION = "advbox-positional-1"
_MAX_CHARS_PER_PAGE = 200_000
_MAX_CHUNKS_PER_PAGE = 15_000
_MAX_SECONDS = 30
_PROCESS = re.compile(r"^\s*Processo\b", re.IGNORECASE)
_FOLDER = re.compile(r"^\s*Pasta\s*:?\s*$", re.IGNORECASE)
_REPORT = re.compile(r"\bRelat[oó]rio\b", re.IGNORECASE)
_EMPTY = re.compile(r"\bNenhum\s+processo\b", re.IGNORECASE)
_CNJ = re.compile(r"(?<!\d)(\d{7}[-.]?\d{2}[.]?\d{4}[.]?\d{1}[.]?\d{2}[.]?\d{4})(?!\d)")
_FOLDER_VALUE = re.compile(r"[\w./-]{1,80}", re.UNICODE)


@dataclass(frozen=True)
class ManifestItem:
    manifest_item_id: uuid.UUID
    source_ordinal: int
    process_number_normalized: str | None
    folder_exact: str | None
    source_page_start: int
    source_page_end: int
    quality_flags: tuple[str, ...]


@dataclass(frozen=True)
class ParsedManifest:
    source_sha256: str
    parser_version: str
    layout_version: str
    page_count: int
    items: tuple[ManifestItem, ...]
    quality_flags: tuple[str, ...]


@dataclass(frozen=True)
class _Chunk:
    text: str
    x: float
    y: float


def _page_chunks(page, deadline: float) -> tuple[_Chunk, ...]:
    if page.get("/Contents") is None:
        raise PdfRejected("TEXT_LAYER_REQUIRED")
    chunks: list[_Chunk] = []
    characters = 0

    def visit(text, cm, tm, font, font_size):
        nonlocal characters
        if time.monotonic() > deadline or len(chunks) >= _MAX_CHUNKS_PER_PAGE:
            raise PdfRejected("PARSER_LIMIT_EXCEEDED")
        characters += len(text)
        if characters > _MAX_CHARS_PER_PAGE:
            raise PdfRejected("PARSER_LIMIT_EXCEEDED")
        if text.strip():
            chunks.append(_Chunk(text.strip(), float(tm[4]), float(tm[5])))

    page.extract_text(visitor_text=visit)
    if not chunks:
        raise PdfRejected("TEXT_LAYER_REQUIRED")
    return tuple(chunks)


def _folder_for(anchor: _Chunk, chunks: tuple[_Chunk, ...]) -> tuple[str | None, bool]:
    labels = [
        chunk
        for chunk in chunks
        if _FOLDER.fullmatch(chunk.text)
        and abs(chunk.x - 93) <= 12
        and 48 <= chunk.y - anchor.y <= 65
    ]
    if len(labels) != 1:
        return None, False
    label = labels[0]
    values = [
        chunk
        for chunk in chunks
        if 122 <= chunk.x <= 160 and abs(chunk.y - label.y) <= 3 and chunk.text != label.text
    ]
    if len(values) != 1:
        return None, False
    value = unicodedata.normalize("NFC", values[0].text.strip())
    if not _FOLDER_VALUE.fullmatch(value):
        return None, False
    return value, True


def parse_pdf_manifest(content: bytes) -> ParsedManifest:
    """Parse in memory; never return or log free text from the source."""
    validated = validate_pdf(content)
    deadline = time.monotonic() + _MAX_SECONDS
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.pages[0].get("/Contents") is None:
            raise PdfRejected("TEXT_LAYER_REQUIRED")
        heading = reader.pages[0].extract_text(extraction_mode="layout") or ""
        if len(heading) > _MAX_CHARS_PER_PAGE:
            raise PdfRejected("PARSER_LIMIT_EXCEEDED")
        pages = [_page_chunks(page, deadline) for page in reader.pages]
    except PdfRejected:
        raise
    except (PdfReadError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise PdfRejected("PDF_MALFORMED") from exc

    heading_lines = [line.strip() for line in heading.splitlines() if line.strip()]
    if not _REPORT.search(heading):
        raise PdfRejected("LAYOUT_UNKNOWN")
    if not all(page for page in pages):
        raise PdfRejected("TEXT_LAYER_REQUIRED")

    items: list[ManifestItem] = []
    mutable: list[dict] = []
    for page_number, chunks in enumerate(pages, start=1):
        anchors = [
            chunk for chunk in chunks if _PROCESS.match(chunk.text) and abs(chunk.x - 2) <= 10
        ]
        anchors.sort(key=lambda chunk: chunk.y)
        if not anchors and mutable:
            mutable[-1]["page_end"] = page_number
        for anchor in anchors:
            folder, has_folder = _folder_for(anchor, chunks)
            match = _CNJ.search(anchor.text)
            number = normalize_process_number(match.group(1)) if match else None
            flags: set[str] = set()
            if not has_folder:
                flags.add("incomplete_block")
            if number is None and re.search(r"\d", anchor.text):
                flags.add("invalid_identifier")
            if number is None and folder is None:
                flags.add("missing_identifier")
            mutable.append(
                {
                    "ordinal": len(mutable) + 1,
                    "number": number,
                    "folder": folder,
                    "page_start": page_number,
                    "page_end": page_number,
                    "flags": flags,
                }
            )
    if not mutable:
        if not any(_EMPTY.search(line) for line in heading_lines[:15]):
            raise PdfRejected("LAYOUT_UNKNOWN")
        return ParsedManifest(
            validated.source_sha256,
            PARSER_VERSION,
            LAYOUT_VERSION,
            validated.page_count,
            (),
            ("zero_processes",),
        )

    seen: set[tuple[str, str]] = set()
    for raw in mutable:
        key = ("number", raw["number"]) if raw["number"] else ("folder", raw["folder"] or "")
        if key[1]:
            if key in seen:
                raw["flags"].add("duplicate_source")
            seen.add(key)
        if raw["page_end"] > raw["page_start"]:
            raw["flags"].add("page_continuation")
        ordinal = raw["ordinal"]
        item_id = uuid.uuid5(
            uuid.NAMESPACE_URL, f"{validated.source_sha256}:{PARSER_VERSION}:{ordinal}"
        )
        items.append(
            ManifestItem(
                item_id,
                ordinal,
                raw["number"],
                raw["folder"],
                raw["page_start"],
                raw["page_end"],
                tuple(sorted(raw["flags"])),
            )
        )
    return ParsedManifest(
        validated.source_sha256,
        PARSER_VERSION,
        LAYOUT_VERSION,
        validated.page_count,
        tuple(items),
        (),
    )

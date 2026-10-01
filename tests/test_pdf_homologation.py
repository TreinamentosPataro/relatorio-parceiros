"""Count-only PDF-7 dry-run tests with synthetic PDFs and API transport."""

import asyncio
import io
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import SecretStr
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import func, select

from partner_reports.config import AppEnvironment
from partner_reports.integrations.advbox.client import (
    AdvboxClient,
    AdvboxUnexpectedResponse,
    ConservativeRateLimiter,
)
from partner_reports.integrations.advbox.config import AdvboxAuditSettings
from partner_reports.pdf_imports.homologation import (
    execute_private_dry_run,
    inspect_private_corpus,
)
from partner_reports.pdf_imports.homologation_cli import _safe_failure_code
from partner_reports.pdf_imports.private_pass import PreparedPrivatePass, persist_private_pass
from partner_reports.pdf_imports.reconciliation import (
    ApiCandidate,
    ApiSnapshot,
    _snapshot_digest,
    reconcile_items,
    summarize,
)
from partner_reports.pdf_imports.storage import LocalPrivatePdfStorage
from partner_reports.persistence.models import Partner, PdfImportBatch, PdfImportReview


def _pdf(number: str, folder: str) -> bytes:
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
        "\n".join(
            (
                "BT /F1 10 Tf 2 700 Td (Relatorio) Tj ET",
                f"BT /F1 10 Tf 2 123 Td (Processo {number}) Tj ET",
                "BT /F1 10 Tf 93 179 Td (Pasta) Tj ET",
                f"BT /F1 10 Tf 136 179 Td ({folder}) Tj ET",
                "BT /F1 10 Tf 100 300 Td (Texto privado sintetico descartado) Tj ET",
            )
        ).encode("ascii")
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _settings() -> AdvboxAuditSettings:
    return AdvboxAuditSettings(  # type: ignore[call-arg]
        advbox_api_token=SecretStr("synthetic-token"), advbox_audit_max_retries=0
    )


def test_private_corpus_summary_never_returns_names_hashes_or_text(tmp_path: Path) -> None:
    private = tmp_path / "private"
    private.mkdir()
    private.joinpath("sensitive-source-name.pdf").write_bytes(
        _pdf("1234567-89.2026.1.23.4567", "PASTA-01")
    )
    corpus = inspect_private_corpus(private)
    assert corpus.source_files == corpus.unique_sources == corpus.manifest_items == 1
    assert corpus.rejected == {}
    public = repr(corpus)
    assert "sensitive-source-name" not in public
    assert "Texto privado" not in public
    assert corpus.manifests[0].source_sha256 not in public


def test_private_dry_run_is_count_only_and_get_only(tmp_path: Path) -> None:
    private = tmp_path / "private"
    private.mkdir()
    private.joinpath("source.pdf").write_bytes(_pdf("1234567-89.2026.1.23.4567", "PASTA-01"))
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 1,
                        "process_number": "1234567-89.2026.1.23.4567",
                        "folder": "PASTA-01",
                        "customers": [],
                        "responsible": "Synthetic Person",
                    }
                ],
                "totalCount": 1,
                "limit": int(request.url.params["limit"]),
                "offset": 0,
            },
        )

    async def execute() -> dict:
        client = AdvboxClient(
            _settings(),
            transport=httpx.MockTransport(handler),
            limiter=ConservativeRateLimiter(20, sleep=lambda _: asyncio.sleep(0), clock=lambda: 0),
        )
        try:
            return await execute_private_dry_run(private, client)
        finally:
            await client.aclose()

    result = asyncio.run(execute())
    assert result["reconciliation"] == {
        "total": 1,
        "matched": 1,
        "unmatched": 0,
        "ambiguous": 0,
        "duplicate_source": 0,
        "invalid_identifier": 0,
    }
    assert result["persistence"] == {
        "source_rows_written": 0,
        "api_rows_written": 0,
        "links_written": 0,
        "reports_generated": 0,
    }
    assert methods == ["GET", "GET"]
    rendered = str(result)
    assert "Synthetic Person" not in rendered
    assert "1234567" not in rendered
    assert "PASTA-01" not in rendered


def test_private_dry_run_detects_duplicate_across_source_files(tmp_path: Path) -> None:
    private = tmp_path / "private"
    private.mkdir()
    source = _pdf("1234567-89.2026.1.23.4567", "PASTA-01")
    private.joinpath("first.pdf").write_bytes(source)
    private.joinpath("second.pdf").write_bytes(source + b"\n")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 1,
                        "process_number": "1234567-89.2026.1.23.4567",
                        "folder": "PASTA-01",
                        "customers": [],
                    }
                ],
                "totalCount": 1,
                "limit": int(request.url.params["limit"]),
                "offset": 0,
            },
        )

    async def execute() -> dict:
        client = AdvboxClient(
            _settings(),
            transport=httpx.MockTransport(handler),
            limiter=ConservativeRateLimiter(20, sleep=lambda _: asyncio.sleep(0), clock=lambda: 0),
        )
        try:
            return await execute_private_dry_run(private, client)
        finally:
            await client.aclose()

    result = asyncio.run(execute())
    assert result["reconciliation"] == {
        "total": 2,
        "matched": 0,
        "unmatched": 0,
        "ambiguous": 0,
        "duplicate_source": 2,
        "invalid_identifier": 0,
    }


def test_snapshot_change_has_sanitized_failure_code() -> None:
    error = AdvboxUnexpectedResponse("origem mudou entre leituras")
    assert _safe_failure_code(error) == "ADVBOX_SNAPSHOT_CONTENT_CHANGED"


def test_authorized_private_pass_persists_exact_and_pending_without_links(
    tmp_path: Path, db_session
) -> None:
    private = tmp_path / "private"
    private.mkdir()
    private.joinpath("first.pdf").write_bytes(_pdf("1234567-89.2026.1.23.4567", "PASTA-01"))
    private.joinpath("second.pdf").write_bytes(_pdf("123", "PASTA-02"))
    corpus = inspect_private_corpus(private)
    candidates = (ApiCandidate(1, "12345678920261234567", "PASTA-01", "synthetic-digest"),)
    snapshot = ApiSnapshot(_snapshot_digest(candidates), 1, datetime.now(UTC), candidates)
    summaries = tuple(
        asdict(summarize(reconcile_items(manifest.items, snapshot)))
        for manifest in corpus.manifests
    )
    prepared = PreparedPrivatePass(corpus, snapshot, summaries)
    batches_before = db_session.scalar(select(func.count()).select_from(PdfImportBatch))
    reviews_before = db_session.scalar(select(func.count()).select_from(PdfImportReview))

    result = persist_private_pass(
        db_session,
        LocalPrivatePdfStorage(tmp_path / "objects", AppEnvironment.DEVELOPMENT),
        private,
        prepared,
        environment=AppEnvironment.DEVELOPMENT,
    )

    assert result == {
        "source_rows_written": 2,
        "batch_rows_written": 2,
        "reconciliation_runs_written": 2,
        "pending_decisions_written": 1,
        "active_links_written": 0,
        "report_versions_written": 0,
    }
    private_partners = db_session.scalars(
        select(Partner).where(Partner.external_id.in_(("PDF7-PRIVATE-001", "PDF7-PRIVATE-002")))
    ).all()
    assert len(private_partners) == 2
    assert all(partner.status == "inactive" for partner in private_partners)
    assert db_session.scalar(select(func.count()).select_from(PdfImportBatch)) == batches_before + 2
    assert (
        db_session.scalar(select(func.count()).select_from(PdfImportReview)) == reviews_before + 1
    )
    pending = db_session.scalar(
        select(PdfImportReview).where(
            PdfImportReview.reason_code == "INVALID_IDENTIFIER_ACCEPTED_PENDING"
        )
    )
    assert pending is not None and pending.before_advbox_id is None

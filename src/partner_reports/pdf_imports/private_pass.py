"""Authorized local persistence and count-only preview for PDF-7."""

import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from playwright.async_api import async_playwright
from sqlalchemy import select
from sqlalchemy.orm import Session

from partner_reports.config import AppEnvironment
from partner_reports.pdf_imports.homologation import PrivateCorpus, inspect_private_corpus
from partner_reports.pdf_imports.processing import parse_quarantined_batch
from partner_reports.pdf_imports.reconciliation import (
    ApiSnapshot,
    MatchStatus,
    collect_verified_snapshot,
    reconcile_items,
    summarize,
)
from partner_reports.pdf_imports.reconciliation_service import (
    persist_authorized_private_reconciliation,
)
from partner_reports.pdf_imports.service import receive_pdf
from partner_reports.pdf_imports.storage import LocalPrivatePdfStorage
from partner_reports.pdf_imports.validation import validate_pdf
from partner_reports.persistence.models import (
    AppUser,
    Partner,
    PdfImportBatch,
    PdfImportReview,
    PdfReconciliationItem,
)

AUTHORIZATION_CODE = "PDF7_OWNER_APPROVED_2026-09-25"


@dataclass(frozen=True)
class PreparedPrivatePass:
    corpus: PrivateCorpus
    snapshot: ApiSnapshot
    summaries: tuple[dict[str, int], ...]


async def prepare_private_pass(input_directory: Path, client) -> PreparedPrivatePass:
    """Require a stable snapshot and accept only exact matches or explicit invalid IDs."""
    corpus = inspect_private_corpus(input_directory)
    if corpus.rejected or len(corpus.manifests) != corpus.source_files:
        raise ValueError("PDF7_PRIVATE_CORPUS_REJECTED")
    snapshot = await collect_verified_snapshot(client)
    all_items = tuple(item for manifest in corpus.manifests for item in manifest.items)
    aggregate = summarize(reconcile_items(all_items, snapshot))
    if aggregate.unmatched or aggregate.ambiguous or aggregate.duplicate_source:
        raise ValueError("PDF7_RECONCILIATION_NOT_EXCLUSIVE")
    summaries = tuple(
        asdict(summarize(reconcile_items(manifest.items, snapshot)))
        for manifest in corpus.manifests
    )
    return PreparedPrivatePass(corpus, snapshot, summaries)


def _actor(db: Session) -> AppUser:
    subject = "local:pdf7-authorized-owner"
    actor = db.scalar(select(AppUser).where(AppUser.external_subject == subject))
    if actor is None:
        actor = AppUser(
            external_subject=subject,
            display_name="Responsável autorizado PDF-7",
            status="active",
        )
        db.add(actor)
        db.flush()
    return actor


def _partner(db: Session, ordinal: int) -> Partner:
    external_id = f"PDF7-PRIVATE-{ordinal:03d}"
    partner = db.scalar(select(Partner).where(Partner.external_id == external_id))
    if partner is None:
        partner = Partner(external_id=external_id, name=external_id, status="inactive")
        db.add(partner)
        db.flush()
    elif partner.status != "inactive":
        partner.status = "inactive"
    return partner


def persist_private_pass(
    db: Session,
    storage: LocalPrivatePdfStorage,
    input_directory: Path,
    prepared: PreparedPrivatePass,
    *,
    environment: AppEnvironment,
) -> dict[str, int]:
    """Persist the authorized corpus with opaque partners and pending invalid items."""
    if environment is not AppEnvironment.DEVELOPMENT:
        raise ValueError("PDF7_PRIVATE_ENVIRONMENT_BLOCKED")
    paths = sorted(
        path
        for path in input_directory.resolve(strict=True).iterdir()
        if path.is_file() and path.suffix == ".pdf"
    )
    if len(paths) != len(prepared.corpus.manifests):
        raise ValueError("PDF7_PRIVATE_CORPUS_CHANGED")
    actor = _actor(db)
    period_end = prepared.snapshot.verified_at.date()
    period_start = date(period_end.year, period_end.month, 1)
    source_rows = batch_rows = run_rows = pending_rows = 0
    for ordinal, path in enumerate(paths, start=1):
        partner = _partner(db, ordinal)
        validated = validate_pdf(path.read_bytes())
        expected = prepared.corpus.manifests[ordinal - 1]
        if validated.source_sha256 != expected.source_sha256:
            raise ValueError("PDF7_PRIVATE_CORPUS_CHANGED")
        received = receive_pdf(
            db,
            storage,
            validated,
            partner_id=partner.id,
            period_start=period_start,
            period_end=period_end,
            uploaded_by=actor.id,
        )
        batch = received.batch
        if received.duplicate:
            if batch.partner_id != partner.id:
                raise ValueError("PDF7_PRIVATE_SOURCE_ALREADY_ASSIGNED")
        else:
            source_rows += 1
            batch_rows += 1
        if batch.state == "quarantined":
            manifest = parse_quarantined_batch(db, storage, batch.id)
            if manifest is None:
                raise ValueError("PDF7_PRIVATE_PARSE_FAILED")
        prior_runs = db.scalar(
            select(PdfImportBatch.review_revision).where(PdfImportBatch.id == batch.id)
        )
        run = persist_authorized_private_reconciliation(
            db,
            batch.id,
            prepared.snapshot,
            environment=environment,
            authorization_code=AUTHORIZATION_CODE,
        )
        if batch.review_revision != prior_runs:
            run_rows += 1
        invalid_items = db.scalars(
            select(PdfReconciliationItem).where(
                PdfReconciliationItem.run_id == run.id,
                PdfReconciliationItem.status == MatchStatus.INVALID_IDENTIFIER,
            )
        ).all()
        for item in invalid_items:
            existing = db.scalar(
                select(PdfImportReview.id).where(
                    PdfImportReview.batch_id == batch.id,
                    PdfImportReview.reconciliation_run_id == run.id,
                    PdfImportReview.reconciliation_item_id == item.id,
                    PdfImportReview.reason_code == "INVALID_IDENTIFIER_ACCEPTED_PENDING",
                )
            )
            if existing is not None:
                continue
            batch.review_revision += 1
            db.add(
                PdfImportReview(
                    batch_id=batch.id,
                    reviewer_user_id=actor.id,
                    decision="returned",
                    reason_code="INVALID_IDENTIFIER_ACCEPTED_PENDING",
                    reconciliation_item_id=item.id,
                    reconciliation_run_id=run.id,
                    review_revision=batch.review_revision,
                )
            )
            pending_rows += 1
    db.flush()
    return {
        "source_rows_written": source_rows,
        "batch_rows_written": batch_rows,
        "reconciliation_runs_written": run_rows,
        "pending_decisions_written": pending_rows,
        "active_links_written": 0,
        "report_versions_written": 0,
    }


def _preview_html(prepared: PreparedPrivatePass) -> str:
    rows = "".join(
        "<tr>"
        f"<td>Fonte privada {index:03d}</td>"
        f"<td>{summary['total']}</td>"
        f"<td>{summary['matched']}</td>"
        f"<td>{summary['invalid_identifier']}</td>"
        "</tr>"
        for index, summary in enumerate(prepared.summaries, start=1)
    )
    totals = asdict(
        summarize(
            reconcile_items(
                tuple(item for manifest in prepared.corpus.manifests for item in manifest.items),
                prepared.snapshot,
            )
        )
    )
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 18mm; }}
body {{ font: 14px Arial, sans-serif; color: #171717; }}
h1 {{ border-bottom: 3px solid #b9933f; padding-bottom: 10px; }}
.notice {{ background: #f5edda; border-left: 5px solid #b9933f; padding: 12px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 18px; }}
th, td {{ border-bottom: 1px solid #bbb; padding: 8px; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
.total {{ font-weight: bold; }}
</style></head><body>
<h1>Prévia interna de homologação PDF-7</h1>
<p class="notice">Conteúdo técnico, privado e não publicável.
Identificadores inválidos permanecem sem vínculo.</p>
<p>Parser: {prepared.corpus.parser_version} · Layout: {prepared.corpus.layout_version}</p>
<table><thead><tr><th>Origem opaca</th><th>Itens</th>
<th>Correspondências</th><th>Pendências</th></tr></thead>
<tbody>{rows}<tr class="total"><td>Total</td><td>{totals["total"]}</td>
<td>{totals["matched"]}</td><td>{totals["invalid_identifier"]}</td>
</tr></tbody></table>
<p>Ambíguos: {totals["ambiguous"]} · Ausentes: {totals["unmatched"]} ·
Duplicados: {totals["duplicate_source"]}</p>
</body></html>"""


async def render_private_preview(prepared: PreparedPrivatePass) -> tuple[str, bytes]:
    """Render one PII-free internal preview from aggregate counts only."""
    html = _preview_html(prepared)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            await page.route("**/*", lambda route: route.abort())
            await page.set_content(html, wait_until="load")
            pdf = await page.pdf(format="A4", print_background=True)
        finally:
            await browser.close()
    if not pdf.startswith(b"%PDF"):
        raise ValueError("PDF7_PRIVATE_PREVIEW_FAILED")
    return html, pdf


def write_private_preview(output_directory: Path, html: str, pdf: bytes) -> None:
    """Atomically write the ignored private preview after the database commit."""
    output = output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for filename, content in (
        ("preview_internal.html", html.encode()),
        ("preview_internal.pdf", pdf),
    ):
        descriptor, temporary_name = tempfile.mkstemp(prefix=".pending-", dir=output)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, output / filename)
        finally:
            Path(temporary_name).unlink(missing_ok=True)

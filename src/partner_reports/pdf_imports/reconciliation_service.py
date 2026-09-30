"""Count-only dry-run and explicitly gated persistence of exact match proposals."""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from partner_reports.config import AppEnvironment, Settings
from partner_reports.integrations.advbox.client import AdvboxClient
from partner_reports.partner_scope import partner_in_scope
from partner_reports.pdf_imports.lifecycle import PdfBatchState, require_transition
from partner_reports.pdf_imports.parser import ManifestItem
from partner_reports.pdf_imports.reconciliation import (
    ApiCandidate,
    ApiSnapshot,
    MatchResult,
    MatchStatus,
    ReconciliationSummary,
    collect_verified_snapshot,
    reconcile_items,
    require_snapshot_integrity,
    summarize,
)
from partner_reports.persistence.models import (
    Customer,
    Lawsuit,
    LawsuitCustomer,
    Partner,
    PdfImportBatch,
    PdfImportEvent,
    PdfManifestItem,
    PdfReconciliationItem,
    PdfReconciliationRun,
)


def _minimal_candidate_digest(candidate: ApiCandidate) -> str:
    encoded = json.dumps(
        [
            candidate.external_id,
            candidate.process_number_normalized,
            candidate.folder_exact,
            candidate.customer_external_ids,
        ],
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _persist_minimal_matched_snapshot(
    db: Session, snapshot: ApiSnapshot, results: tuple[MatchResult, ...]
) -> None:
    """Persist only matched lawsuits and referenced customer IDs, never names or free text."""

    matched_ids = {
        result.matched_advbox_id for result in results if result.status is MatchStatus.MATCHED
    }
    candidates = {
        candidate.external_id: candidate
        for candidate in snapshot.candidates
        if candidate.external_id in matched_ids
    }
    if set(candidates) != matched_ids:
        raise ValueError("fotografia mínima inconsistente")
    now = datetime.now(UTC)
    customer_external_ids = {
        customer_id
        for candidate in candidates.values()
        for customer_id in candidate.customer_external_ids
    }
    customers = {
        row.advbox_id: row
        for row in db.scalars(select(Customer).where(Customer.advbox_id.in_(customer_external_ids)))
    }
    for external_id in customer_external_ids - customers.keys():
        row = Customer(
            advbox_id=external_id,
            report_hash=hashlib.sha256(f"technical-id:{external_id}".encode()).hexdigest(),
            synced_at=now,
            status="active",
        )
        db.add(row)
        customers[external_id] = row
    db.flush()

    lawsuits = {
        row.advbox_id: row
        for row in db.scalars(select(Lawsuit).where(Lawsuit.advbox_id.in_(matched_ids)))
    }
    for external_id, candidate in candidates.items():
        lawsuit = lawsuits.get(external_id)
        if lawsuit is None:
            lawsuit = Lawsuit(advbox_id=external_id)
            db.add(lawsuit)
            lawsuits[external_id] = lawsuit
        lawsuit.process_number = candidate.process_number_normalized
        lawsuit.folder = candidate.folder_exact
        lawsuit.report_hash = _minimal_candidate_digest(candidate)
        lawsuit.synced_at = now
        lawsuit.status = "active"
        lawsuit.deleted_at = None
    db.flush()

    for external_id, candidate in candidates.items():
        lawsuit = lawsuits[external_id]
        existing = {
            row.customer_id: row
            for row in db.scalars(
                select(LawsuitCustomer).where(LawsuitCustomer.lawsuit_id == lawsuit.id)
            )
        }
        desired = {customers[customer_id].id for customer_id in candidate.customer_external_ids}
        for customer_id, link in existing.items():
            if customer_id not in desired:
                db.delete(link)
        for customer_id in desired - existing.keys():
            db.add(LawsuitCustomer(lawsuit_id=lawsuit.id, customer_id=customer_id))
    db.flush()


def _manifest(db: Session, batch: PdfImportBatch) -> tuple[ManifestItem, ...]:
    rows = db.scalars(
        select(PdfManifestItem)
        .where(PdfManifestItem.batch_id == batch.id)
        .order_by(PdfManifestItem.source_ordinal)
    ).all()
    if batch.parsed_item_count != len(rows):
        raise ValueError("manifesto técnico incompleto")
    if [row.source_ordinal for row in rows] != list(range(1, len(rows) + 1)):
        raise ValueError("ordinais do manifesto inconsistentes")
    return tuple(
        ManifestItem(
            row.id,
            row.source_ordinal,
            row.process_number_normalized,
            row.folder_exact,
            row.source_page_start,
            row.source_page_end,
            tuple(row.quality_flags),
        )
        for row in rows
    )


async def dry_run_batch(
    db: Session, client: AdvboxClient, batch_id: uuid.UUID
) -> ReconciliationSummary:
    """Read the official GET-only API and return aggregate counts; no writes."""
    batch = db.get(PdfImportBatch, batch_id)
    if batch is None or batch.state not in {PdfBatchState.PARSED, PdfBatchState.NEEDS_REVIEW}:
        raise ValueError("lote indisponível para reconciliação")
    items = _manifest(db, batch)
    snapshot = await collect_verified_snapshot(client)
    return summarize(reconcile_items(items, snapshot))


def _persist_reconciliation(
    db: Session,
    batch_id: uuid.UUID,
    snapshot: ApiSnapshot,
    *,
    persist_minimal_snapshot: bool = False,
) -> PdfReconciliationRun:
    batch = db.get(PdfImportBatch, batch_id, with_for_update=True)
    if batch is None or batch.state not in {PdfBatchState.PARSED, PdfBatchState.NEEDS_REVIEW}:
        raise ValueError("lote indisponível para reconciliação")
    if batch.parser_version is None:
        raise ValueError("parser não versionado")
    require_snapshot_integrity(snapshot)
    age = datetime.now(UTC) - snapshot.verified_at
    if age < timedelta(seconds=0) or age > timedelta(minutes=5):
        raise ValueError("fotografia técnica expirada")

    previous = db.scalar(
        select(PdfReconciliationRun).where(
            PdfReconciliationRun.batch_id == batch.id,
            PdfReconciliationRun.snapshot_sha256 == snapshot.sha256,
            PdfReconciliationRun.parser_version == batch.parser_version,
        )
    )
    if previous is not None:
        if persist_minimal_snapshot:
            _persist_minimal_matched_snapshot(
                db, snapshot, reconcile_items(_manifest(db, batch), snapshot)
            )
        return previous

    items = _manifest(db, batch)
    results = reconcile_items(items, snapshot)
    if persist_minimal_snapshot:
        _persist_minimal_matched_snapshot(db, snapshot, results)
    summary = summarize(results)
    run = PdfReconciliationRun(
        batch_id=batch.id,
        created_at=datetime.now(UTC),
        parser_version=batch.parser_version,
        snapshot_sha256=snapshot.sha256,
        snapshot_total=snapshot.total,
        snapshot_verified_at=snapshot.verified_at,
        result_total=summary.total,
        matched_count=summary.matched,
        unmatched_count=summary.unmatched,
        ambiguous_count=summary.ambiguous,
        duplicate_source_count=summary.duplicate_source,
        invalid_identifier_count=summary.invalid_identifier,
    )
    db.add(run)
    db.flush()
    internal_ids = {
        row.advbox_id: row.id
        for row in db.scalars(
            select(Lawsuit).where(
                Lawsuit.advbox_id.in_(
                    [
                        result.matched_advbox_id
                        for result in results
                        if result.status is MatchStatus.MATCHED
                    ]
                )
            )
        )
    }
    for result in results:
        matched = result.status is MatchStatus.MATCHED
        evidence = (
            hashlib.sha256(
                f"{batch.id}:{batch.parser_version}:{snapshot.sha256}:"
                f"{result.manifest_item_id}:{result.matched_advbox_id}:{result.method}".encode()
            ).hexdigest()
            if matched
            else None
        )
        db.add(
            PdfReconciliationItem(
                run_id=run.id,
                manifest_item_id=result.manifest_item_id,
                status=result.status,
                method=result.method if matched else None,
                reason_code=result.reason_code,
                matched_advbox_id=result.matched_advbox_id if matched else None,
                matched_lawsuit_id=internal_ids.get(result.matched_advbox_id) if matched else None,
                evidence_sha256=evidence,
                proposed_valid_from=batch.period_start if matched else None,
                proposed_valid_to=batch.period_end if matched else None,
            )
        )
    require_transition(batch.state, PdfBatchState.RECONCILING)
    db.add(
        PdfImportEvent(
            batch_id=batch.id, from_state=batch.state, to_state=PdfBatchState.RECONCILING
        )
    )
    batch.state = PdfBatchState.RECONCILING
    require_transition(batch.state, PdfBatchState.NEEDS_REVIEW)
    db.add(
        PdfImportEvent(
            batch_id=batch.id,
            from_state=batch.state,
            to_state=PdfBatchState.NEEDS_REVIEW,
            reason_code="awaiting_human_review",
        )
    )
    batch.state = PdfBatchState.NEEDS_REVIEW
    batch.review_revision += 1
    db.flush()
    return run


def persist_synthetic_reconciliation(
    db: Session,
    batch_id: uuid.UUID,
    snapshot: ApiSnapshot,
    *,
    environment: AppEnvironment,
) -> PdfReconciliationRun:
    """Store proposals only for synthetic partners, including production-like validation."""
    batch = db.get(PdfImportBatch, batch_id)
    partner = db.get(Partner, batch.partner_id) if batch is not None else None
    if partner is None or not partner.external_id.startswith("SYNTHETIC-"):
        raise ValueError("persistência restrita a parceiro sintético")
    return _persist_reconciliation(db, batch_id, snapshot)


def persist_scoped_reconciliation(
    db: Session,
    batch_id: uuid.UUID,
    snapshot: ApiSnapshot,
    *,
    settings: Settings,
) -> PdfReconciliationRun:
    """Persist proposals only when the batch partner is in the configured data scope."""

    batch = db.get(PdfImportBatch, batch_id)
    partner = db.get(Partner, batch.partner_id) if batch is not None else None
    if not partner_in_scope(settings, partner):
        raise ValueError("parceiro fora do escopo de dados")
    return _persist_reconciliation(db, batch_id, snapshot, persist_minimal_snapshot=True)


def persist_authorized_private_reconciliation(
    db: Session,
    batch_id: uuid.UUID,
    snapshot: ApiSnapshot,
    *,
    environment: AppEnvironment,
    authorization_code: str,
) -> PdfReconciliationRun:
    """Store one explicitly authorized PDF-7 proposal set in local development only."""
    if environment is not AppEnvironment.DEVELOPMENT:
        raise ValueError("homologação privada permitida somente em desenvolvimento")
    if authorization_code != "PDF7_OWNER_APPROVED_2026-09-25":
        raise ValueError("autorização da homologação privada ausente")
    batch = db.get(PdfImportBatch, batch_id)
    partner = db.get(Partner, batch.partner_id) if batch is not None else None
    if partner is None or not partner.external_id.startswith("PDF7-PRIVATE-"):
        raise ValueError("parceiro fora do escopo privado autorizado")
    return _persist_reconciliation(db, batch_id, snapshot)

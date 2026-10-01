"""Transactional, scoped PDF review. No publication occurs in this service."""

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from partner_reports.config import AppEnvironment, Settings
from partner_reports.partner_scope import partner_in_scope
from partner_reports.pdf_imports.lifecycle import require_transition
from partner_reports.persistence.models import (
    Lawsuit,
    Partner,
    PartnerCaseLink,
    PdfImportBatch,
    PdfImportEvent,
    PdfImportReview,
    PdfManifestItem,
    PdfReconciliationItem,
    PdfReconciliationRun,
)


class ReviewConflict(ValueError):
    """A stale form or invalid review decision."""


def _locked_batch(
    db: Session,
    batch_id: uuid.UUID,
    revision: int,
    environment: AppEnvironment,
    settings: Settings | None = None,
) -> PdfImportBatch:
    batch = db.get(PdfImportBatch, batch_id)
    if batch is None:
        raise ReviewConflict("Lote indisponível")
    db.scalar(select(Partner.id).where(Partner.id == batch.partner_id).with_for_update())
    batch = db.get(PdfImportBatch, batch_id, with_for_update=True, populate_existing=True)
    partner = db.get(Partner, batch.partner_id)
    if not partner_in_scope(settings, partner):
        raise ReviewConflict("Revisão restrita a dados sintéticos ou a parceiro liberado")
    if batch.review_revision != revision:
        raise ReviewConflict("Lote modificado por outra decisão")
    return batch


def _latest_run(db: Session, batch: PdfImportBatch) -> PdfReconciliationRun:
    run = db.scalar(
        select(PdfReconciliationRun)
        .where(PdfReconciliationRun.batch_id == batch.id)
        .order_by(PdfReconciliationRun.created_at.desc(), PdfReconciliationRun.id.desc())
        .limit(1)
    )
    if run is None or run.parser_version != batch.parser_version:
        raise ReviewConflict("Reconciliação atual indisponível")
    return run


def reprocessing_pending(db: Session, batch: PdfImportBatch, run: PdfReconciliationRun) -> bool:
    """A request remains pending until a newer reconciliation run exists."""
    latest_request = db.scalar(
        select(PdfImportReview)
        .where(
            PdfImportReview.batch_id == batch.id,
            PdfImportReview.decision == "reprocess_requested",
        )
        .order_by(PdfImportReview.review_revision.desc())
        .limit(1)
    )
    if latest_request is None or latest_request.reconciliation_run_id != run.id:
        return False
    return not (
        batch.processing_status == "succeeded"
        and batch.processing_finished_at is not None
        and batch.processing_finished_at > latest_request.created_at
    )


def _record(
    db: Session,
    batch: PdfImportBatch,
    actor_id: uuid.UUID,
    decision: str,
    reason: str,
    *,
    item_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    before_id: int | None = None,
    after_id: int | None = None,
    method: str | None = None,
    replacement_id: uuid.UUID | None = None,
) -> PdfImportReview:
    batch.review_revision += 1
    row = PdfImportReview(
        batch_id=batch.id,
        reviewer_user_id=actor_id,
        decision=decision,
        reason_code=reason,
        reconciliation_item_id=item_id,
        reconciliation_run_id=run_id,
        before_advbox_id=before_id,
        after_advbox_id=after_id,
        method=method,
        replacement_batch_id=replacement_id,
        review_revision=batch.review_revision,
    )
    db.add(row)
    db.flush()
    return row


def _transition(
    db: Session, batch: PdfImportBatch, state: str, actor_id: uuid.UUID, reason: str
) -> None:
    require_transition(batch.state, state)
    db.add(
        PdfImportEvent(
            batch_id=batch.id,
            actor_user_id=actor_id,
            from_state=batch.state,
            to_state=state,
            reason_code=reason,
        )
    )
    batch.state = state


def reject_batch(
    db: Session,
    batch_id: uuid.UUID,
    revision: int,
    actor_id: uuid.UUID,
    *,
    environment: AppEnvironment,
    settings: Settings | None = None,
) -> PdfImportReview:
    batch = _locked_batch(db, batch_id, revision, environment, settings)
    if batch.state not in {"quarantined", "parsing", "needs_review"}:
        raise ReviewConflict("Rejeição indisponível neste estado")
    _transition(db, batch, "rejected", actor_id, "review_rejected")
    return _record(db, batch, actor_id, "rejected", "SOURCE_REJECTED")


def request_reprocessing(
    db: Session,
    batch_id: uuid.UUID,
    revision: int,
    actor_id: uuid.UUID,
    *,
    environment: AppEnvironment,
    settings: Settings | None = None,
) -> PdfImportReview:
    batch = _locked_batch(db, batch_id, revision, environment, settings)
    if batch.state in {"quarantined", "parsed"} and batch.processing_status == "failed":
        # Automatic attempts are exhausted; the same PDF cannot be uploaded again.
        review = _record(db, batch, actor_id, "reprocess_requested", "PROCESSING_RETRY")
    elif batch.state == "needs_review":
        run = _latest_run(db, batch)
        if reprocessing_pending(db, batch, run):
            raise ReviewConflict("Reprocessamento já solicitado para esta reconciliação")
        review = _record(
            db, batch, actor_id, "reprocess_requested", "SOURCE_REPROCESS", run_id=run.id
        )
    else:
        raise ReviewConflict("Reprocessamento indisponível neste estado")
    batch.processing_status = "pending"
    batch.processing_attempt_count = 0
    batch.processing_available_at = None
    batch.processing_finished_at = None
    batch.processing_error_code = None
    return review


def correct_item(
    db: Session,
    batch_id: uuid.UUID,
    item_id: uuid.UUID,
    advbox_id: int,
    revision: int,
    actor_id: uuid.UUID,
    *,
    environment: AppEnvironment,
    enabled: bool,
    settings: Settings | None = None,
) -> PdfImportReview:
    if not enabled:
        raise ReviewConflict("Exceções aguardam regra aprovada")
    batch = _locked_batch(db, batch_id, revision, environment, settings)
    if batch.state != "needs_review":
        raise ReviewConflict("Correção indisponível neste estado")
    run = _latest_run(db, batch)
    if reprocessing_pending(db, batch, run):
        raise ReviewConflict("Reprocessamento pendente")
    item = db.get(PdfReconciliationItem, item_id)
    if item is None or item.run_id != run.id or item.status not in {"unmatched", "ambiguous"}:
        raise ReviewConflict("Item não elegível para correção")
    lawsuit = db.scalar(
        select(Lawsuit).where(Lawsuit.advbox_id == advbox_id, Lawsuit.status == "active")
    )
    if lawsuit is None:
        raise ReviewConflict("ID técnico inexistente")
    return _record(
        db,
        batch,
        actor_id,
        "corrected",
        "EXISTING_ID_CONFIRMED",
        item_id=item.id,
        run_id=run.id,
        after_id=advbox_id,
        method="manual_existing_id",
    )


def _approved_items(
    db: Session, batch: PdfImportBatch, *, allow_corrections: bool
) -> list[tuple[PdfReconciliationItem, Lawsuit, str, str]]:
    if (
        batch.state != "needs_review"
        or batch.parser_version is None
        or batch.parsed_item_count is None
    ):
        raise ReviewConflict("Lote não está pronto para aprovação")
    run = _latest_run(db, batch)
    if reprocessing_pending(db, batch, run):
        raise ReviewConflict("Reprocessamento pendente")
    manifest = db.scalars(select(PdfManifestItem).where(PdfManifestItem.batch_id == batch.id)).all()
    if len(manifest) != batch.parsed_item_count or any(
        set(row.quality_flags) - {"page_continuation"} for row in manifest
    ):
        raise ReviewConflict("Manifesto incompleto ou com erro")
    items = db.scalars(
        select(PdfReconciliationItem).where(PdfReconciliationItem.run_id == run.id)
    ).all()
    if not items or len(items) != batch.parsed_item_count or len(items) != run.result_total:
        raise ReviewConflict("Classificação incompleta ou carteira vazia sem confirmação")
    corrections = {
        row.reconciliation_item_id: row
        for row in db.scalars(
            select(PdfImportReview)
            .where(
                PdfImportReview.batch_id == batch.id,
                PdfImportReview.decision == "corrected",
                PdfImportReview.reconciliation_item_id.in_([item.id for item in items]),
            )
            .order_by(PdfImportReview.review_revision)
        )
    }
    resolved = []
    seen: set[int] = set()
    for item in items:
        correction = corrections.get(item.id)
        if item.status == "matched":
            if (
                item.matched_lawsuit_id is None
                or item.matched_advbox_id is None
                or item.evidence_sha256 is None
                or item.method is None
            ):
                raise ReviewConflict("Processo local ou evidência ausente")
            lawsuit = db.get(Lawsuit, item.matched_lawsuit_id)
            if (
                lawsuit is None
                or lawsuit.advbox_id != item.matched_advbox_id
                or lawsuit.status != "active"
            ):
                raise ReviewConflict("Processo local divergente")
            method, evidence = item.method, item.evidence_sha256
        elif item.status in {"unmatched", "ambiguous"} and correction is not None:
            if not allow_corrections:
                raise ReviewConflict("Exceções aguardam regra aprovada")
            lawsuit = db.scalar(
                select(Lawsuit).where(
                    Lawsuit.advbox_id == correction.after_advbox_id, Lawsuit.status == "active"
                )
            )
            if lawsuit is None:
                raise ReviewConflict("Correção técnica obsoleta")
            method = "manual_existing_id"
            evidence = hashlib.sha256(
                f"{batch.id}:{run.id}:{item.id}:{lawsuit.advbox_id}:{correction.id}".encode()
            ).hexdigest()
        else:
            raise ReviewConflict("Ambiguidade ou erro sem resolução")
        if lawsuit.advbox_id in seen:
            raise ReviewConflict("Processo repetido no lote")
        seen.add(lawsuit.advbox_id)
        resolved.append((item, lawsuit, method, evidence))
    return resolved


def approve_batch(
    db: Session,
    batch_id: uuid.UUID,
    revision: int,
    actor_id: uuid.UUID,
    *,
    environment: AppEnvironment,
    four_eyes: bool,
    allow_corrections: bool = False,
    replace_batch_id: uuid.UUID | None = None,
    settings: Settings | None = None,
) -> PdfImportReview:
    batch = _locked_batch(db, batch_id, revision, environment, settings)
    if four_eyes and batch.uploaded_by == actor_id:
        raise ReviewConflict("Outro administrador deve aprovar este lote")
    resolved = _approved_items(db, batch, allow_corrections=allow_corrections)
    old = None
    if replace_batch_id is not None:
        old = db.get(PdfImportBatch, replace_batch_id, with_for_update=True, populate_existing=True)
        if (
            old is None
            or old.id == batch.id
            or old.state != "approved"
            or old.partner_id != batch.partner_id
            or old.period_start != batch.period_start
            or old.period_end != batch.period_end
        ):
            raise ReviewConflict("Lote substituído inválido")
    existing = db.scalars(
        select(PdfImportBatch).where(
            PdfImportBatch.partner_id == batch.partner_id,
            PdfImportBatch.period_start == batch.period_start,
            PdfImportBatch.period_end == batch.period_end,
            PdfImportBatch.state == "approved",
        )
    ).all()
    if any(row.id != replace_batch_id for row in existing) or (existing and old is None):
        raise ReviewConflict("Já existe lote aprovado para este período")
    if old is not None:
        for link in db.scalars(
            select(PartnerCaseLink).where(
                PartnerCaseLink.pdf_batch_id == old.id, PartnerCaseLink.status == "active"
            )
        ):
            link.status = "inactive"
            link.updated_by = actor_id
        _transition(db, old, "superseded", actor_id, "review_superseded")
        old.superseded_by_batch_id = batch.id
        _record(db, old, actor_id, "superseded", "PERIOD_REPLACED", replacement_id=batch.id)
        db.flush()
    now = datetime.now(UTC)
    for item, lawsuit, method, evidence in resolved:
        db.add(
            PartnerCaseLink(
                partner_id=batch.partner_id,
                advbox_entity_type="lawsuit",
                advbox_entity_id=lawsuit.advbox_id,
                lawsuit_id=lawsuit.id,
                valid_from=batch.period_start,
                valid_to=batch.period_end,
                source="pdf_manifest",
                status="active",
                created_by=actor_id,
                pdf_batch_id=batch.id,
                pdf_reconciliation_item_id=item.id,
                match_method=method,
                evidence_sha256=evidence,
                reviewed_by=actor_id,
                reviewed_at=now,
            )
        )
    _transition(db, batch, "approved", actor_id, "review_approved")
    review = _record(
        db, batch, actor_id, "approved", "EXACT_MATCHES_CONFIRMED", replacement_id=replace_batch_id
    )
    db.flush()
    return review

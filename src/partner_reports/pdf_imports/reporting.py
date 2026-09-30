"""Scoped PDF-batch report input; only structured, minimized fields cross the boundary."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from partner_reports.config import AppEnvironment, Settings
from partner_reports.contracts.view_model import InternalReportViewModel
from partner_reports.domain.report_view import (
    RULE_VERSION,
    PortfolioSnapshot,
    SnapshotCase,
    SnapshotCustomer,
    SnapshotLink,
    SnapshotMovement,
    build_internal_report,
)
from partner_reports.partner_scope import partner_in_scope
from partner_reports.persistence.models import (
    Customer,
    Lawsuit,
    LawsuitCustomer,
    Movement,
    Partner,
    PartnerCaseLink,
    PdfImportBatch,
    PdfImportReview,
    PdfManifestItem,
    PdfReconciliationItem,
    PdfReconciliationRun,
    PdfSourceDocument,
)


class BatchReportUnavailable(ValueError):
    """The approved synthetic batch does not have a complete technical snapshot."""


@dataclass(frozen=True)
class BatchReportInput:
    batch_id: uuid.UUID
    partner_id: uuid.UUID
    revision_key: str
    as_of: datetime
    period_start: date
    snapshot: PortfolioSnapshot

    def build(self, *, generated_at: datetime, version: int) -> InternalReportViewModel:
        return build_internal_report(
            self.snapshot,
            as_of=self.as_of,
            period_start=self.period_start,
            generated_at=generated_at,
            report_version=version,
        )


def _synthetic_runtime(environment: AppEnvironment) -> None:
    if not isinstance(environment, AppEnvironment):
        raise BatchReportUnavailable("ambiente de relatório inválido")


def _revision_key(
    batch: PdfImportBatch, source: PdfSourceDocument, run: PdfReconciliationRun
) -> str:
    components = {
        "partner": str(batch.partner_id),
        "period_start": batch.period_start.isoformat(),
        "period_end": batch.period_end.isoformat(),
        "pdf_sha256": source.source_sha256,
        "parser_version": batch.parser_version,
        "api_snapshot_sha256": run.snapshot_sha256,
        "rule_version": RULE_VERSION,
    }
    return hashlib.sha256(json.dumps(components, sort_keys=True).encode()).hexdigest()


def load_batch_report(
    db: Session,
    batch_id: uuid.UUID,
    *,
    environment: AppEnvironment,
    settings: Settings | None = None,
) -> BatchReportInput:
    """Require approved exact links and a verified snapshot; never read free-text fields."""

    _synthetic_runtime(environment)
    batch = db.get(PdfImportBatch, batch_id)
    if batch is None or batch.state != "approved" or batch.parser_version is None:
        raise BatchReportUnavailable("lote não aprovado")
    partner = db.execute(
        select(
            Partner.id,
            Partner.external_id,
            Partner.status,
            Partner.deleted_at,
            Partner.pilot_enabled,
        ).where(Partner.id == batch.partner_id)
    ).one_or_none()
    source = db.get(PdfSourceDocument, batch.source_document_id)
    if (
        partner is None
        or not partner_in_scope(settings, partner)
        or partner.status != "active"
        or partner.deleted_at is not None
        or source is None
    ):
        raise BatchReportUnavailable("fonte fora do escopo")
    run = db.scalar(
        select(PdfReconciliationRun)
        .where(PdfReconciliationRun.batch_id == batch.id)
        .order_by(PdfReconciliationRun.created_at.desc(), PdfReconciliationRun.id.desc())
        .limit(1)
    )
    if (
        run is None
        or run.parser_version != batch.parser_version
        or run.result_total != batch.parsed_item_count
        or run.snapshot_total < run.result_total
        or run.snapshot_verified_at.tzinfo is None
        or run.snapshot_verified_at.astimezone(UTC).date() != batch.period_end
    ):
        raise BatchReportUnavailable("fotografia da API incompleta ou fora do período")
    manifest_flags = db.scalars(
        select(PdfManifestItem.quality_flags).where(PdfManifestItem.batch_id == batch.id)
    ).all()
    items = db.scalars(
        select(PdfReconciliationItem).where(PdfReconciliationItem.run_id == run.id)
    ).all()
    links = db.scalars(
        select(PartnerCaseLink).where(
            PartnerCaseLink.pdf_batch_id == batch.id,
            PartnerCaseLink.status == "active",
            PartnerCaseLink.source == "pdf_manifest",
        )
    ).all()
    if (
        len(manifest_flags) != run.result_total
        or len(items) != run.result_total
        or len(links) != run.result_total
        or any(set(flags) - {"page_continuation"} for flags in manifest_flags)
        or {link.pdf_reconciliation_item_id for link in links} != {item.id for item in items}
        or any(link.reviewed_at is None or link.lawsuit_id is None for link in links)
    ):
        raise BatchReportUnavailable("revisão ou vínculos incompletos")
    item_by_id = {item.id: item for item in items}
    for link in links:
        item = item_by_id[link.pdf_reconciliation_item_id]
        if item.status == "matched":
            consistent = (
                link.lawsuit_id == item.matched_lawsuit_id
                and link.advbox_entity_id == item.matched_advbox_id
                and link.match_method == item.method
                and link.evidence_sha256 == item.evidence_sha256
            )
        else:
            correction = db.scalar(
                select(PdfImportReview)
                .where(
                    PdfImportReview.batch_id == batch.id,
                    PdfImportReview.reconciliation_item_id == item.id,
                    PdfImportReview.decision == "corrected",
                )
                .order_by(PdfImportReview.review_revision.desc())
                .limit(1)
            )
            consistent = (
                correction is not None
                and link.match_method == "manual_existing_id"
                and link.advbox_entity_id == correction.after_advbox_id
            )
        if not consistent:
            raise BatchReportUnavailable("vínculo diverge da revisão")
    case_ids = {link.lawsuit_id for link in links}
    lawsuits = db.execute(
        select(Lawsuit.id, Lawsuit.status, Lawsuit.updated_at).where(Lawsuit.id.in_(case_ids))
    ).all()
    if len(lawsuits) != len(case_ids) or any(row.status != "active" for row in lawsuits):
        raise BatchReportUnavailable("processo normalizado ausente")
    relationships = db.execute(
        select(
            LawsuitCustomer.lawsuit_id,
            LawsuitCustomer.customer_id,
            LawsuitCustomer.updated_at,
        ).where(LawsuitCustomer.lawsuit_id.in_(case_ids))
    ).all()
    customer_ids = {row.customer_id for row in relationships}
    customers = db.execute(
        select(Customer.id, Customer.status, Customer.updated_at).where(
            Customer.id.in_(customer_ids)
        )
    ).all()
    if len(customers) != len(customer_ids) or any(row.status != "active" for row in customers):
        raise BatchReportUnavailable("cliente normalizado ausente")
    all_links = db.scalars(
        select(PartnerCaseLink).where(
            PartnerCaseLink.status == "active",
            (
                (PartnerCaseLink.lawsuit_id.in_(case_ids))
                | (PartnerCaseLink.customer_id.in_(customer_ids))
            ),
        )
    ).all()
    movements = db.execute(
        select(Movement.lawsuit_id, Movement.occurred_at, Movement.updated_at).where(
            Movement.lawsuit_id.in_(case_ids)
        )
    ).all()
    as_of = run.snapshot_verified_at.astimezone(UTC)
    normalized_cutoff = run.created_at.astimezone(UTC)
    if any(
        row.updated_at > normalized_cutoff
        for row in (*lawsuits, *customers, *relationships, *movements)
    ):
        raise BatchReportUnavailable("dados normalizados posteriores à fotografia")
    snapshot = PortfolioSnapshot(
        partner_id=partner.id,
        partner_code=partner.external_id,
        customers=tuple(SnapshotCustomer(row.id) for row in customers),
        cases=tuple(
            SnapshotCase(
                row.id,
                tuple(rel.customer_id for rel in relationships if rel.lawsuit_id == row.id),
            )
            for row in lawsuits
        ),
        links=tuple(
            SnapshotLink(
                row.partner_id,
                row.advbox_entity_type,
                row.lawsuit_id if row.lawsuit_id is not None else row.customer_id,
                row.valid_from,
                row.valid_to,
                row.status,
            )
            for row in all_links
        ),
        movements=tuple(SnapshotMovement(row.lawsuit_id, row.occurred_at) for row in movements),
        # The verified batch scan is a synthetic technical fixture only. A real
        # source-completeness contract must be approved before this can run there.
        source_complete=True,
        linkage_approved=True,
        source_synced_at=as_of,
        linkage_validated_at=max(link.reviewed_at for link in links) if links else as_of,
    )
    if any(
        link.lawsuit_id not in case_ids
        or link.partner_id != partner.id
        or link.valid_from > batch.period_end
        or (link.valid_to is not None and link.valid_to < batch.period_end)
        for link in links
    ):
        raise BatchReportUnavailable("vínculo fora da carteira ou período")
    revision_key = _revision_key(batch, source, run)
    return BatchReportInput(batch.id, partner.id, revision_key, as_of, batch.period_start, snapshot)

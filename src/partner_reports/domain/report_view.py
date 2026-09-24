"""Pure, deterministic portfolio projection; no raw API or free text is accepted."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from partner_reports.contracts.common import AvailabilityStatus
from partner_reports.contracts.view_model import (
    CaseView,
    CustomerView,
    DistributionSet,
    InternalQuality,
    InternalReportViewModel,
    MetricSet,
    PortfolioTotals,
    QualityAlert,
    ReportMetadata,
    ReportValue,
    ReportViewModel,
    SafePartnerIdentity,
)

RULE_VERSION = "portfolio_snapshot_v1"
SOURCE = "advbox_normalized"
LINK_SOURCE = "governed_partner_mapping"


@dataclass(frozen=True)
class SnapshotCustomer:
    id: uuid.UUID


@dataclass(frozen=True)
class SnapshotCase:
    id: uuid.UUID
    customer_ids: tuple[uuid.UUID, ...] = ()


@dataclass(frozen=True)
class SnapshotLink:
    partner_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    valid_from: date
    valid_to: date | None = None
    status: str = "active"

    def is_effective_on(self, day: date) -> bool:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("vigência de vínculo inválida")
        return (
            self.status == "active"
            and self.valid_from <= day
            and (self.valid_to is None or day <= self.valid_to)
        )


@dataclass(frozen=True)
class SnapshotMovement:
    lawsuit_id: uuid.UUID
    occurred_at: datetime


@dataclass(frozen=True)
class PortfolioSnapshot:
    partner_id: uuid.UUID
    partner_code: str
    customers: tuple[SnapshotCustomer, ...]
    cases: tuple[SnapshotCase, ...]
    links: tuple[SnapshotLink, ...]
    movements: tuple[SnapshotMovement, ...]
    source_complete: bool = False
    linkage_approved: bool = False
    source_synced_at: datetime | None = None
    linkage_validated_at: datetime | None = None


def _value(
    value: object,
    *,
    as_of: datetime,
    source: str,
    validated_at: datetime | None = None,
) -> ReportValue:
    return ReportValue(
        status=AvailabilityStatus.AVAILABLE,
        value=value,
        source=source,
        as_of=as_of,
        last_validated_at=validated_at,
    )


def _pending(*, as_of: datetime, source: str, reason: str) -> ReportValue:
    return ReportValue(
        status=AvailabilityStatus.PENDING_VALIDATION,
        value=None,
        source=source,
        as_of=as_of,
        reason_code=reason,
    )


def _missing(*, as_of: datetime, source: str, reason: str) -> ReportValue:
    return ReportValue(
        status=AvailabilityStatus.NOT_PROVIDED,
        value=None,
        source=source,
        as_of=as_of,
        reason_code=reason,
    )


def _classify(
    snapshot: PortfolioSnapshot, as_of: datetime
) -> tuple[dict[uuid.UUID, set[uuid.UUID]], dict[uuid.UUID, set[uuid.UUID]], int, int, int]:
    customer_ids = {customer.id for customer in snapshot.customers}
    case_ids = {case.id for case in snapshot.cases}
    if len(customer_ids) != len(snapshot.customers) or len(case_ids) != len(snapshot.cases):
        raise ValueError("snapshot contém IDs técnicos duplicados")
    customer_partners: dict[uuid.UUID, set[uuid.UUID]] = {
        customer_id: set() for customer_id in customer_ids
    }
    direct_case_partners: dict[uuid.UUID, set[uuid.UUID]] = {case_id: set() for case_id in case_ids}
    nonexistent_links = 0
    nonexistent_target_links = 0
    for link in snapshot.links:
        if not link.is_effective_on(as_of.date()):
            continue
        if link.entity_type == "customer" and link.entity_id in customer_partners:
            customer_partners[link.entity_id].add(link.partner_id)
        elif link.entity_type == "lawsuit" and link.entity_id in direct_case_partners:
            direct_case_partners[link.entity_id].add(link.partner_id)
        elif link.entity_type not in {"customer", "lawsuit"}:
            raise ValueError("tipo de vínculo desconhecido")
        else:
            nonexistent_links += 1
            nonexistent_target_links += link.partner_id == snapshot.partner_id
    case_partners: dict[uuid.UUID, set[uuid.UUID]] = {}
    missing_references = 0
    for case in snapshot.cases:
        partners = set(direct_case_partners[case.id])
        for customer_id in set(case.customer_ids):
            if customer_id not in customer_ids:
                missing_references += 1
            else:
                partners.update(customer_partners[customer_id])
        case_partners[case.id] = partners
    return (
        customer_partners,
        case_partners,
        missing_references,
        nonexistent_links,
        nonexistent_target_links,
    )


def build_internal_report(
    snapshot: PortfolioSnapshot,
    *,
    as_of: datetime,
    period_start: date,
    generated_at: datetime,
    report_version: int = 1,
) -> InternalReportViewModel:
    """Return audit-safe quality data and a partner preview only behind technical gates."""

    if as_of.tzinfo is None or generated_at.tzinfo is None:
        raise ValueError("instantes do relatório exigem fuso horário")
    if period_start > as_of.date() or generated_at < as_of or report_version < 1:
        raise ValueError("período, geração ou versão inválidos")
    if snapshot.source_synced_at is not None and snapshot.source_synced_at.tzinfo is None:
        raise ValueError("sincronização exige fuso horário")
    if snapshot.linkage_validated_at is not None and snapshot.linkage_validated_at.tzinfo is None:
        raise ValueError("validação de vínculo exige fuso horário")
    if snapshot.source_synced_at is not None and snapshot.source_synced_at > as_of:
        raise ValueError("sincronização posterior ao corte")
    if snapshot.linkage_validated_at is not None and snapshot.linkage_validated_at > generated_at:
        raise ValueError("validação posterior à geração")
    customer_index = {customer.id: customer for customer in snapshot.customers}
    case_index = {case.id: case for case in snapshot.cases}
    (
        customer_partners,
        case_partners,
        missing_references,
        nonexistent_links,
        nonexistent_target_links,
    ) = _classify(snapshot, as_of)
    target = snapshot.partner_id
    eligible_case_ids = tuple(
        sorted(
            (case_id for case_id, partners in case_partners.items() if partners == {target}),
            key=lambda identifier: identifier.hex,
        )
    )
    eligible_customer_ids = {
        customer_id for customer_id, partners in customer_partners.items() if partners == {target}
    }
    for case_id in eligible_case_ids:
        eligible_customer_ids.update(
            customer_id
            for customer_id in case_index[case_id].customer_ids
            if customer_id in customer_index
        )
    sorted_customer_ids = tuple(
        sorted(eligible_customer_ids, key=lambda identifier: identifier.hex)
    )
    ambiguous = sum(target in partners and len(partners) > 1 for partners in case_partners.values())
    unlinked = sum(not partners for partners in case_partners.values())
    movement_dates: dict[uuid.UUID, datetime] = {}
    for movement in snapshot.movements:
        if movement.occurred_at.tzinfo is None:
            raise ValueError("andamento exige fuso horário")
        if movement.lawsuit_id not in case_index or movement.occurred_at > as_of:
            continue
        previous = movement_dates.get(movement.lawsuit_id)
        if previous is None or movement.occurred_at > previous:
            movement_dates[movement.lawsuit_id] = movement.occurred_at
    missing_movements = sum(case_id not in movement_dates for case_id in eligible_case_ids)
    relevant_missing_references = sum(
        customer_id not in customer_index
        for case_id in eligible_case_ids
        for customer_id in set(case_index[case_id].customer_ids)
    )
    quality = InternalQuality(
        unlinked_lawsuits=unlinked,
        ambiguous_lawsuits=ambiguous,
        missing_customer_references=missing_references,
        nonexistent_link_references=nonexistent_links,
        missing_movements=missing_movements,
    )
    technical_ready = (
        snapshot.source_complete
        and snapshot.source_synced_at is not None
        and snapshot.linkage_approved
        and snapshot.linkage_validated_at is not None
        and ambiguous == 0
        and nonexistent_target_links == 0
    )
    preview = (
        _build_partner_preview(
            snapshot,
            as_of=as_of,
            period_start=period_start,
            generated_at=generated_at,
            report_version=report_version,
            customer_ids=sorted_customer_ids,
            case_ids=eligible_case_ids,
            case_index=case_index,
            movement_dates=movement_dates,
            missing_references=relevant_missing_references,
        )
        if technical_ready
        else None
    )
    return InternalReportViewModel(
        partner_id=target,
        as_of=as_of,
        rule_version=RULE_VERSION,
        quality=(
            _value(quality, as_of=as_of, source=LINK_SOURCE)
            if snapshot.source_complete and snapshot.source_synced_at is not None
            else _pending(as_of=as_of, source=SOURCE, reason="incomplete_source_scan")
        ),
        linked_case_ids=(
            _value(eligible_case_ids, as_of=as_of, source=LINK_SOURCE)
            if technical_ready
            else _pending(
                as_of=as_of, source=LINK_SOURCE, reason="linkage_not_approved_or_conflict"
            )
        ),
        linked_customer_ids=(
            _value(sorted_customer_ids, as_of=as_of, source=LINK_SOURCE)
            if technical_ready
            else _pending(
                as_of=as_of, source=LINK_SOURCE, reason="linkage_not_approved_or_conflict"
            )
        ),
        partner_preview=preview,
    )


def _build_partner_preview(
    snapshot: PortfolioSnapshot,
    *,
    as_of: datetime,
    period_start: date,
    generated_at: datetime,
    report_version: int,
    customer_ids: tuple[uuid.UUID, ...],
    case_ids: tuple[uuid.UUID, ...],
    case_index: dict[uuid.UUID, SnapshotCase],
    movement_dates: dict[uuid.UUID, datetime],
    missing_references: int,
) -> ReportViewModel:
    customer_references = {
        customer_id: f"C-{index:03d}" for index, customer_id in enumerate(customer_ids, start=1)
    }
    case_references = {case_id: f"L-{index:03d}" for index, case_id in enumerate(case_ids, start=1)}
    customers: list[CustomerView] = []
    link_validation = snapshot.linkage_validated_at
    for customer_id in customer_ids:
        related = tuple(
            case_references[case_id]
            for case_id in case_ids
            if customer_id in case_index[case_id].customer_ids
        )
        customers.append(
            CustomerView(
                reference=_value(
                    customer_references[customer_id],
                    as_of=as_of,
                    source=LINK_SOURCE,
                    validated_at=link_validation,
                ),
                lawsuit_references=_value(
                    related, as_of=as_of, source=LINK_SOURCE, validated_at=link_validation
                ),
            )
        )
    cases: list[CaseView] = []
    for case_id in case_ids:
        related = tuple(
            customer_references[customer_id]
            for customer_id in customer_ids
            if customer_id in case_index[case_id].customer_ids
        )
        latest = movement_dates.get(case_id)
        cases.append(
            CaseView(
                reference=_value(
                    case_references[case_id],
                    as_of=as_of,
                    source=LINK_SOURCE,
                    validated_at=link_validation,
                ),
                customer_references=_value(
                    related, as_of=as_of, source=LINK_SOURCE, validated_at=link_validation
                ),
                latest_recorded_movement_at=(
                    _value(
                        latest,
                        as_of=as_of,
                        source="advbox.last_movements",
                        validated_at=snapshot.source_synced_at,
                    )
                    if latest is not None
                    else _missing(as_of=as_of, source="advbox.last_movements", reason="no_movement")
                ),
                latest_relevant_movement_at=_pending(
                    as_of=as_of, source="legal_review", reason="relevance_rule_unapproved"
                ),
                executive_status=_pending(
                    as_of=as_of, source="legal_review", reason="executive_rule_unapproved"
                ),
            )
        )
    metrics = MetricSet(
        unique_customers=_value(
            len(customer_ids), as_of=as_of, source=LINK_SOURCE, validated_at=link_validation
        ),
        lawsuits=_value(
            len(case_ids), as_of=as_of, source=LINK_SOURCE, validated_at=link_validation
        ),
        benefits_granted=_pending(as_of=as_of, source="business_rules", reason="kpi_unapproved"),
        in_financial=_pending(as_of=as_of, source="business_rules", reason="kpi_unapproved"),
        in_judicial=_pending(as_of=as_of, source="business_rules", reason="kpi_unapproved"),
    )
    distributions = DistributionSet(
        by_stage=_pending(as_of=as_of, source="business_rules", reason="stage_mapping_unapproved"),
        by_legal_status=_pending(
            as_of=as_of, source="business_rules", reason="legal_status_rule_unapproved"
        ),
        by_area=_pending(as_of=as_of, source="business_rules", reason="area_mapping_unapproved"),
    )
    alerts: list[QualityAlert] = []
    missing_movements = sum(case_id not in movement_dates for case_id in case_ids)
    if missing_movements:
        alerts.append(
            QualityAlert(
                code="missing_movement",
                count=_value(missing_movements, as_of=as_of, source="advbox.last_movements"),
            )
        )
    if missing_references:
        alerts.append(
            QualityAlert(
                code="missing_customer_reference",
                count=_value(missing_references, as_of=as_of, source=SOURCE),
            )
        )
    alerts.append(
        QualityAlert(
            code="freshness_threshold_pending",
            count=_pending(as_of=as_of, source="business_rules", reason="threshold_unapproved"),
        )
    )
    return ReportViewModel(
        partner=_value(
            SafePartnerIdentity(code=snapshot.partner_code),
            as_of=as_of,
            source=LINK_SOURCE,
            validated_at=link_validation,
        ),
        metadata=_value(
            ReportMetadata(
                period_start=period_start,
                period_end=as_of.date(),
                as_of=as_of,
                generated_at=generated_at,
                report_version=report_version,
                rule_version=RULE_VERSION,
            ),
            as_of=as_of,
            source="report_builder",
            validated_at=snapshot.source_synced_at,
        ),
        origin=_value(
            SOURCE, as_of=as_of, source="synchronization", validated_at=snapshot.source_synced_at
        ),
        summary=_value(
            PortfolioTotals(unique_customers=len(customer_ids), lawsuits=len(case_ids)),
            as_of=as_of,
            source=LINK_SOURCE,
            validated_at=link_validation,
        ),
        metrics=metrics,
        distributions=distributions,
        customers=_value(
            tuple(customers), as_of=as_of, source=LINK_SOURCE, validated_at=link_validation
        ),
        cases=_value(tuple(cases), as_of=as_of, source=LINK_SOURCE, validated_at=link_validation),
        financial=_pending(
            as_of=as_of, source="finance_approval", reason="allocation_rule_unapproved"
        ),
        alerts=_value(tuple(alerts), as_of=as_of, source="quality_rules"),
        publication_ready=False,
    )

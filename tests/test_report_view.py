"""Only synthetic portfolio snapshots; legacy cases are reconciled conceptually."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from partner_reports.contracts.common import AvailabilityStatus
from partner_reports.contracts.view_model import (
    NonNegativeInt,
    ReportMetadata,
    ReportValue,
    ReportViewModel,
)
from partner_reports.domain.report_view import (
    PortfolioSnapshot,
    SnapshotCase,
    SnapshotCustomer,
    SnapshotLink,
    SnapshotMovement,
    build_internal_report,
)

PARTNER_A = uuid.UUID(int=10)
PARTNER_B = uuid.UUID(int=20)
AS_OF = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def _id(number: int) -> uuid.UUID:
    return uuid.UUID(int=number)


def _build(snapshot: PortfolioSnapshot):
    return build_internal_report(
        snapshot,
        as_of=AS_OF,
        period_start=date(2026, 9, 1),
        generated_at=AS_OF + timedelta(minutes=1),
    )


def _snapshot(
    *,
    customer_numbers: tuple[int, ...],
    case_customers: tuple[tuple[int, tuple[int, ...]], ...],
    links: tuple[SnapshotLink, ...],
    movements: tuple[SnapshotMovement, ...] = (),
    source_complete: bool = True,
    linkage_approved: bool = True,
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        partner_id=PARTNER_A,
        partner_code="SYNTHETIC-PARTNER-A",
        customers=tuple(SnapshotCustomer(_id(number)) for number in customer_numbers),
        cases=tuple(
            SnapshotCase(_id(case_number), tuple(_id(number) for number in customers))
            for case_number, customers in case_customers
        ),
        links=links,
        movements=movements,
        source_complete=source_complete,
        linkage_approved=linkage_approved,
        source_synced_at=AS_OF,
        linkage_validated_at=AS_OF if linkage_approved else None,
    )


def _link(entity_type: str, entity_number: int, *, partner_id: uuid.UUID = PARTNER_A, **kwargs):
    return SnapshotLink(
        partner_id=partner_id,
        entity_type=entity_type,
        entity_id=_id(entity_number),
        valid_from=kwargs.pop("valid_from", date(2026, 1, 1)),
        **kwargs,
    )


def test_p017_synthetic_reconciliation_keeps_legal_and_financial_kpis_pending() -> None:
    snapshot = _snapshot(
        customer_numbers=(101, 102),
        case_customers=((201, (101,)), (202, (102,))),
        links=(_link("lawsuit", 201), _link("lawsuit", 202)),
        movements=(SnapshotMovement(_id(202), AS_OF - timedelta(days=1)),),
    )
    internal = _build(snapshot)
    report = internal.partner_preview
    assert report is not None
    assert report.summary.value.unique_customers == 2
    assert report.metadata.status is AvailabilityStatus.AVAILABLE
    assert report.metadata.value.period_end == AS_OF.date()
    assert report.summary.value.lawsuits == 2
    assert report.metrics.unique_customers.value == 2
    assert report.metrics.lawsuits.value == 2
    assert report.metrics.benefits_granted.value is None
    assert report.metrics.in_financial.status is AvailabilityStatus.PENDING_VALIDATION
    assert report.metrics.in_judicial.status is AvailabilityStatus.PENDING_VALIDATION
    assert report.financial.value is None
    assert (
        report.cases.value[0].latest_recorded_movement_at.status is AvailabilityStatus.NOT_PROVIDED
    )
    assert internal.quality.value.missing_movements == 1
    assert report.cases.value[1].latest_recorded_movement_at.value == AS_OF - timedelta(days=1)
    assert report.cases.value[1].latest_relevant_movement_at.value is None
    assert report.publication_ready is False


def test_p004_synthetic_two_customers_three_cases_not_cached_legacy_one() -> None:
    snapshot = _snapshot(
        customer_numbers=(101, 102),
        case_customers=((201, (101,)), (202, (101,)), (203, (102,))),
        links=(_link("customer", 101), _link("customer", 102)),
    )
    report = _build(snapshot).partner_preview
    assert report is not None
    assert report.metrics.unique_customers.value == 2
    assert report.metrics.lawsuits.value == 3
    assert len(report.customers.value[0].lawsuit_references.value) == 2
    assert sum(len(customer.lawsuit_references.value) for customer in report.customers.value) == 3


def test_p026_synthetic_one_case_does_not_sum_overlapping_legacy_cards() -> None:
    snapshot = _snapshot(
        customer_numbers=(101,),
        case_customers=((201, (101,)),),
        links=(_link("customer", 101),),
    )
    report = _build(snapshot).partner_preview
    assert report is not None
    assert report.metrics.lawsuits.value == 1
    assert report.metrics.benefits_granted.value is None
    assert report.metrics.in_financial.value is None
    assert report.metrics.in_judicial.value is None


def test_missing_financial_is_not_zero_and_confirmed_zero_is_valid() -> None:
    report = _build(
        _snapshot(
            customer_numbers=(101,),
            case_customers=((201, (101,)),),
            links=(_link("lawsuit", 201),),
        )
    ).partner_preview
    assert report is not None
    assert report.financial.status is AvailabilityStatus.PENDING_VALIDATION
    assert report.financial.value is None
    zero = ReportValue[int](status="available", value=0, source="synthetic", as_of=AS_OF)
    assert zero.value == 0
    with pytest.raises(ValidationError):
        ReportValue[int](status="available", value=None, source="synthetic", as_of=AS_OF)
    with pytest.raises(ValidationError):
        ReportValue[int](status="not_provided", value=0, source="synthetic", as_of=AS_OF)


def test_ambiguity_blocks_partner_preview_without_silent_precedence() -> None:
    snapshot = _snapshot(
        customer_numbers=(101,),
        case_customers=((201, (101,)),),
        links=(_link("customer", 101), _link("lawsuit", 201, partner_id=PARTNER_B)),
    )
    internal = _build(snapshot)
    assert internal.quality.value.ambiguous_lawsuits == 1
    assert internal.partner_preview is None
    assert internal.linked_case_ids.value is None


@pytest.mark.parametrize("gate", ["source_complete", "linkage_approved"])
def test_incomplete_source_or_unapproved_mapping_blocks_preview(gate: str) -> None:
    options = {gate: False}
    snapshot = _snapshot(
        customer_numbers=(101,),
        case_customers=((201, (101,)),),
        links=(_link("lawsuit", 201),),
        **options,
    )
    internal = _build(snapshot)
    assert internal.partner_preview is None
    assert internal.linked_customer_ids.status is AvailabilityStatus.PENDING_VALIDATION


def test_mapping_validity_and_latest_movement_cutoff() -> None:
    snapshot = _snapshot(
        customer_numbers=(101,),
        case_customers=((201, (101,)),),
        links=(
            _link("lawsuit", 201, valid_to=date(2026, 9, 15)),
            _link("customer", 101, valid_from=date(2026, 9, 16)),
            _link("lawsuit", 201, status="pending"),
        ),
        movements=(
            SnapshotMovement(_id(201), AS_OF - timedelta(days=3)),
            SnapshotMovement(_id(201), AS_OF - timedelta(days=1)),
            SnapshotMovement(_id(201), AS_OF + timedelta(days=1)),
        ),
    )
    report = _build(snapshot).partner_preview
    assert report is not None
    assert report.metrics.lawsuits.value == 1
    assert report.cases.value[0].latest_recorded_movement_at.value == AS_OF - timedelta(days=1)


def test_external_contract_rejects_sensitive_fields_and_keeps_other_partner_out() -> None:
    snapshot = _snapshot(
        customer_numbers=(101, 102),
        case_customers=((201, (101,)), (202, (102,))),
        links=(_link("customer", 101), _link("customer", 102, partner_id=PARTNER_B)),
    )
    report = _build(snapshot).partner_preview
    assert report is not None
    assert report.metrics.unique_customers.value == 1
    assert report.metrics.lawsuits.value == 1
    serialized = report.model_dump_json()
    for forbidden in ("identification", "process_number", "notes", "title", "amount"):
        assert forbidden not in serialized
    with pytest.raises(ValidationError):
        ReportViewModel.model_validate({**report.model_dump(), "notes": "synthetic forbidden"})


def test_missing_customer_reference_is_quality_alert_not_fictitious_customer() -> None:
    snapshot = _snapshot(
        customer_numbers=(101,),
        case_customers=((201, (101, 999)),),
        links=(_link("lawsuit", 201),),
    )
    internal = _build(snapshot)
    report = internal.partner_preview
    assert report is not None
    assert internal.quality.value.missing_customer_references == 1
    assert report.metrics.unique_customers.value == 1
    alerts = {alert.code: alert.count.value for alert in report.alerts.value}
    assert alerts["missing_customer_reference"] == 1


def test_invalid_period_and_duplicate_ids_are_rejected() -> None:
    duplicate = _snapshot(
        customer_numbers=(101, 101),
        case_customers=((201, (101,)),),
        links=(_link("lawsuit", 201),),
    )
    with pytest.raises(ValueError, match="duplicados"):
        _build(duplicate)
    valid = _snapshot(customer_numbers=(), case_customers=(), links=())
    with pytest.raises(ValueError, match="período"):
        build_internal_report(
            valid,
            as_of=AS_OF,
            period_start=date(2026, 9, 17),
            generated_at=AS_OF,
        )


def test_empty_approved_portfolio_is_real_zero_but_missing_approval_date_blocks() -> None:
    empty = _snapshot(customer_numbers=(), case_customers=(), links=())
    report = _build(empty).partner_preview
    assert report is not None
    assert report.metrics.unique_customers.value == 0
    assert report.metrics.lawsuits.value == 0
    assert report.metrics.unique_customers.last_validated_at == AS_OF
    unvalidated = PortfolioSnapshot(**{**empty.__dict__, "linkage_validated_at": None})
    assert _build(unvalidated).partner_preview is None


def test_partner_code_must_be_technical_and_source_time_cannot_exceed_cutoff() -> None:
    base = _snapshot(customer_numbers=(), case_customers=(), links=())
    unsafe_code = PortfolioSnapshot(**{**base.__dict__, "partner_code": "Synthetic Person Name"})
    with pytest.raises(ValidationError):
        _build(unsafe_code)
    future_sync = PortfolioSnapshot(
        **{**base.__dict__, "source_synced_at": AS_OF + timedelta(seconds=1)}
    )
    with pytest.raises(ValueError, match="posterior ao corte"):
        _build(future_sync)


def test_nonexistent_mapping_blocks_preview_and_invalid_validity_is_rejected() -> None:
    snapshot = _snapshot(
        customer_numbers=(101,),
        case_customers=((201, (101,)),),
        links=(_link("lawsuit", 201), _link("lawsuit", 999)),
    )
    internal = _build(snapshot)
    assert internal.quality.value.nonexistent_link_references == 1
    assert internal.partner_preview is None

    invalid = _snapshot(
        customer_numbers=(),
        case_customers=(),
        links=(_link("customer", 101, valid_from=date(2026, 9, 16), valid_to=date(2026, 9, 15)),),
    )
    with pytest.raises(ValueError, match="vigência"):
        _build(invalid)


def test_unlinked_case_count_is_kept_internal() -> None:
    snapshot = _snapshot(
        customer_numbers=(101, 102),
        case_customers=((201, (101,)), (202, (102,))),
        links=(_link("lawsuit", 201),),
    )
    internal = _build(snapshot)
    assert internal.quality.value.unlinked_lawsuits == 1
    assert internal.partner_preview is not None
    assert internal.partner_preview.metrics.lawsuits.value == 1


@pytest.mark.parametrize("bad_value", [-1, True, "1"])
def test_count_contract_rejects_negative_or_coerced_values(bad_value: object) -> None:
    with pytest.raises(ValidationError):
        ReportValue[NonNegativeInt](
            status="available", value=bad_value, source="synthetic", as_of=AS_OF
        )


def test_report_version_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ReportMetadata(
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 16),
            as_of=AS_OF,
            generated_at=AS_OF,
            report_version=0,
            rule_version="synthetic_v1",
        )
    with pytest.raises(ValidationError):
        ReportMetadata(
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 15),
            as_of=AS_OF,
            generated_at=AS_OF,
            report_version=1,
            rule_version="synthetic_v1",
        )


def test_partner_preview_cannot_be_marked_publishable() -> None:
    report = _build(_snapshot(customer_numbers=(), case_customers=(), links=())).partner_preview
    assert report is not None
    with pytest.raises(ValidationError):
        ReportViewModel.model_validate({**report.model_dump(), "publication_ready": True})

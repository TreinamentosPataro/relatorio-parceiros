"""Synthetic tests for ingestion, domain, and report contracts."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from partner_reports.contracts.common import AvailabilityStatus, MoneyValue
from partner_reports.contracts.domain import MappingSource, PartnerCaseLinkInput
from partner_reports.contracts.ingestion import AdvboxMovementInput, AdvboxTransactionInput
from partner_reports.contracts.report import PartnerReport, ReportCase
from partner_reports.domain.partner_linkage import AdvboxEntityType


def test_money_contract_preserves_zero_and_rejects_float() -> None:
    value = MoneyValue(status=AvailabilityStatus.AVAILABLE, value=Decimal("0.00"))

    assert value.value == Decimal("0.00")
    assert value.status is AvailabilityStatus.AVAILABLE

    with pytest.raises(ValidationError):
        MoneyValue(status=AvailabilityStatus.AVAILABLE, value=0.1)


def test_money_contract_separates_absence_from_zero() -> None:
    absent = MoneyValue(status=AvailabilityStatus.NOT_PROVIDED)

    assert absent.value is None
    with pytest.raises(ValidationError):
        MoneyValue(status=AvailabilityStatus.NOT_APPLICABLE, value="0.00")


def test_ingestion_requires_timezone_and_decimal() -> None:
    with pytest.raises(ValidationError):
        AdvboxMovementInput(
            lawsuit_external_id=99,
            source_fingerprint="a" * 64,
            occurred_at=datetime(2026, 1, 1),
        )

    with pytest.raises(ValidationError):
        AdvboxTransactionInput(
            external_id=99,
            amount=1.25,
            amount_status=AvailabilityStatus.AVAILABLE,
        )


def test_link_contract_requires_target_matching_entity_type() -> None:
    with pytest.raises(ValidationError):
        PartnerCaseLinkInput(
            partner_id=uuid.uuid4(),
            entity_type=AdvboxEntityType.CUSTOMER,
            advbox_entity_id=99,
            lawsuit_id=uuid.uuid4(),
            valid_from=date(2026, 1, 1),
            source=MappingSource.ADMIN,
        )


def test_report_contract_is_allowlisted() -> None:
    report = PartnerReport(
        report_version_id=uuid.uuid4(),
        partner_id=uuid.uuid4(),
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        generated_at=datetime(2026, 2, 1, tzinfo=UTC),
        cases=(
            ReportCase(
                case_id=uuid.uuid4(),
                status_key="synthetic_status",
                financial_total=MoneyValue(
                    status=AvailabilityStatus.AVAILABLE,
                    value="10.00",
                ),
            ),
        ),
        sections=(),
    )

    serialized = report.model_dump()
    forbidden = {"notes", "document", "email", "phone", "identification"}
    assert forbidden.isdisjoint(serialized)

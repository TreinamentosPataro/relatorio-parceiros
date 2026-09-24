"""PostgreSQL integrity tests executed only with the migrated development database."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from partner_reports.persistence.models import (
    Customer,
    FinancialTransaction,
    PartnerCaseLink,
    PartnerFinancialAgreement,
)
from partner_reports.persistence.upsert import upsert_customer
from tests.factories import (
    synthetic_customer,
    synthetic_customer_input,
    synthetic_lawsuit,
    synthetic_partner,
)

pytestmark = pytest.mark.database


def test_customer_external_id_is_unique(db_session: Session) -> None:
    db_session.add_all(
        [synthetic_customer(advbox_id=9_000_001), synthetic_customer(advbox_id=9_000_001)]
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_customer_upsert_is_idempotent(db_session: Session) -> None:
    first_id = upsert_customer(db_session, synthetic_customer_input(external_id=9_000_101))
    second_id = upsert_customer(db_session, synthetic_customer_input(external_id=9_000_101))
    count = db_session.scalar(
        select(func.count()).select_from(Customer).where(Customer.advbox_id == 9_000_101)
    )

    assert first_id == second_id
    assert count == 1


def test_money_round_trip_uses_decimal_and_preserves_zero(db_session: Session) -> None:
    transaction = FinancialTransaction(
        advbox_id=9_200_001,
        amount=Decimal("0.00"),
        amount_status="available",
    )
    db_session.add(transaction)
    db_session.flush()
    db_session.expire(transaction)

    assert transaction.amount == Decimal("0.00")
    assert isinstance(transaction.amount, Decimal)


def test_money_status_rejects_implicit_zero_for_missing_data(db_session: Session) -> None:
    transaction = FinancialTransaction(
        advbox_id=9_200_002,
        amount=Decimal("0.00"),
        amount_status="not_provided",
    )
    db_session.add(transaction)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_process_number_is_optional_and_not_unique(db_session: Session) -> None:
    first = synthetic_lawsuit(advbox_id=9_100_001)
    second = synthetic_lawsuit(advbox_id=9_100_002)
    first.process_number = None
    second.process_number = None
    db_session.add_all([first, second])
    db_session.flush()

    assert first.id != second.id


def test_link_target_must_match_entity_type(db_session: Session) -> None:
    partner = synthetic_partner()
    customer = synthetic_customer()
    lawsuit = synthetic_lawsuit()
    db_session.add_all([partner, customer, lawsuit])
    db_session.flush()
    db_session.add(
        PartnerCaseLink(
            partner_id=partner.id,
            advbox_entity_type="customer",
            advbox_entity_id=customer.advbox_id,
            lawsuit_id=lawsuit.id,
            valid_from=date(2026, 1, 1),
            source="admin",
            status="active",
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_link_external_id_must_match_internal_target(db_session: Session) -> None:
    partner = synthetic_partner()
    customer = synthetic_customer()
    db_session.add_all([partner, customer])
    db_session.flush()
    db_session.add(
        PartnerCaseLink(
            partner_id=partner.id,
            advbox_entity_type="customer",
            advbox_entity_id=customer.advbox_id + 1,
            customer_id=customer.id,
            valid_from=date(2026, 1, 1),
            source="admin",
            status="active",
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_active_mapping_periods_cannot_overlap(db_session: Session) -> None:
    first_partner = synthetic_partner(external_id="SYNTHETIC-PARTNER-A")
    second_partner = synthetic_partner(external_id="SYNTHETIC-PARTNER-B")
    customer = synthetic_customer()
    db_session.add_all([first_partner, second_partner, customer])
    db_session.flush()
    db_session.add(
        PartnerCaseLink(
            partner_id=first_partner.id,
            advbox_entity_type="customer",
            advbox_entity_id=customer.advbox_id,
            customer_id=customer.id,
            valid_from=date(2026, 1, 1),
            valid_to=date(2026, 6, 30),
            source="admin",
            status="active",
        )
    )
    db_session.flush()
    db_session.add(
        PartnerCaseLink(
            partner_id=second_partner.id,
            advbox_entity_type="customer",
            advbox_entity_id=customer.advbox_id,
            customer_id=customer.id,
            valid_from=date(2026, 6, 1),
            source="admin",
            status="active",
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_financial_percentage_and_timezone_constraints(db_session: Session) -> None:
    partner = synthetic_partner()
    lawsuit = synthetic_lawsuit()
    db_session.add_all([partner, lawsuit])
    db_session.flush()
    agreement = PartnerFinancialAgreement(
        partner_id=partner.id,
        lawsuit_id=lawsuit.id,
        revenue_type="synthetic_revenue",
        percentage=Decimal("25.1250"),
        deduction_fixed_amount=Decimal("0.10"),
        deduction_percentage=Decimal("2.5000"),
        rounding_mode="half_up",
        rounding_scale=2,
        valid_from=date(2026, 1, 1),
        status="active",
    )
    db_session.add(agreement)
    db_session.flush()

    assert agreement.percentage == Decimal("25.1250")
    assert agreement.created_at.tzinfo is not None

    invalid = PartnerFinancialAgreement(
        id=uuid.uuid4(),
        partner_id=partner.id,
        lawsuit_id=lawsuit.id,
        revenue_type="synthetic_invalid",
        percentage=Decimal("100.0001"),
        deduction_fixed_amount=Decimal("0.00"),
        deduction_percentage=Decimal("0.0000"),
        rounding_mode="half_up",
        rounding_scale=2,
        valid_from=date(2026, 1, 1),
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(invalid)
    with pytest.raises(IntegrityError):
        db_session.flush()

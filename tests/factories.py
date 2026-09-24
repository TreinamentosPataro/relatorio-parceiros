"""Factories containing only obviously synthetic development data."""

from datetime import UTC, datetime

from partner_reports.contracts.ingestion import AdvboxCustomerInput
from partner_reports.persistence.models import Customer, Lawsuit, Partner


def synthetic_partner(*, external_id: str = "SYNTHETIC-PARTNER-001") -> Partner:
    return Partner(external_id=external_id, name="Synthetic Partner", status="active")


def synthetic_customer(*, advbox_id: int = 9_000_001) -> Customer:
    return Customer(
        advbox_id=advbox_id,
        name="Synthetic Customer",
        identification="SYNTHETIC-ID",
        origin="Synthetic Origin",
        source_created_at=datetime(2026, 1, 1, tzinfo=UTC),
        status="active",
    )


def synthetic_customer_input(*, external_id: int = 9_000_101) -> AdvboxCustomerInput:
    return AdvboxCustomerInput(
        external_id=external_id,
        name="Synthetic Customer Input",
        identification="SYNTHETIC-INPUT-ID",
        origin="Synthetic Input Origin",
        source_created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def synthetic_lawsuit(*, advbox_id: int = 9_100_001) -> Lawsuit:
    return Lawsuit(
        advbox_id=advbox_id,
        process_number=None,
        protocol_number=None,
        folder="SYNTHETIC-FOLDER",
        status="active",
    )

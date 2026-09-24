"""Synthetic API/DB tests for page atomicity, resume and idempotence."""

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from partner_reports.integrations.advbox.client import AdvboxTransportError
from partner_reports.jobs.sync import SyncFailure, SyncRunner
from partner_reports.persistence.models import (
    Customer,
    FinancialTransaction,
    Lawsuit,
    LawsuitCustomer,
    Movement,
    PartnerCaseLink,
    SyncChangedPartner,
    SyncError,
    SyncRun,
)
from tests.factories import synthetic_partner

pytestmark = pytest.mark.database


class FakeAdvbox:
    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records
        self.offsets: list[int] = []
        self.fail_once_at: int | None = None
        self.invalid_at: int | None = None

    async def list_page(self, resource: str, *, limit: int, offset: int) -> SimpleNamespace:
        assert resource == "customers"
        self.offsets.append(offset)
        if self.fail_once_at == offset:
            self.fail_once_at = None
            raise AdvboxTransportError("falha sintética")
        if self.invalid_at == offset:
            return SimpleNamespace(payload={"data": [], "totalCount": len(self.records)})
        return SimpleNamespace(
            payload={
                "data": self.records[offset : offset + limit],
                "totalCount": len(self.records),
                "limit": limit,
                "offset": offset,
            }
        )


def _records(count: int) -> list[dict[str, object]]:
    return [{"id": 8_000_000 + i, "name": f"Synthetic Customer {i}"} for i in range(count)]


def _runner(db_session: Session, api: FakeAdvbox) -> SyncRunner:
    connection = db_session.connection()
    factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    return SyncRunner(api, factory)  # type: ignore[arg-type]


def test_all_pages_and_second_load_do_not_duplicate(db_session: Session) -> None:
    api = FakeAdvbox(_records(205))
    runner = _runner(db_session, api)
    first = asyncio.run(runner.run_resource("customers", batch_key="synthetic-first"))
    second = asyncio.run(runner.run_resource("customers", batch_key="synthetic-second"))
    count = db_session.scalar(
        select(func.count())
        .select_from(Customer)
        .where(Customer.advbox_id.between(8_000_000, 8_000_204))
    )

    assert first.status == second.status == "succeeded"
    assert first.pages == second.pages == 3
    assert first.inserted == 205
    assert second.inserted == second.updated == 0
    assert api.offsets == [0, 100, 200, 0, 100, 200]
    assert count == 205


def test_failed_middle_page_resumes_from_committed_checkpoint(db_session: Session) -> None:
    api = FakeAdvbox(_records(201))
    api.fail_once_at = 100
    runner = _runner(db_session, api)
    with pytest.raises(SyncFailure, match="offset=100"):
        asyncio.run(runner.run_resource("customers", batch_key="synthetic-resume"))
    run = db_session.scalar(
        select(SyncRun).where(SyncRun.idempotency_key == "synthetic-resume:customers")
    )
    assert run is not None
    assert run.next_offset == 100
    assert run.status == "partial"

    result = asyncio.run(runner.run_resource("customers", batch_key="synthetic-resume"))
    assert result.status == "succeeded"
    assert result.inserted == 201
    assert result.errors == 0
    assert api.offsets == [0, 100, 100, 200]
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(SyncError)
            .where(SyncError.sync_run_id == run.id, SyncError.resolved_at.is_(None))
        )
        == 0
    )


def test_invalid_page_is_dead_lettered_and_reprocessed(db_session: Session) -> None:
    api = FakeAdvbox(_records(2))
    api.invalid_at = 0
    runner = _runner(db_session, api)
    with pytest.raises(SyncFailure, match="invalid_response"):
        asyncio.run(runner.run_resource("customers", batch_key="synthetic-invalid"))
    api.invalid_at = None
    result = asyncio.run(
        runner.run_resource("customers", batch_key="synthetic-invalid", reprocess=True)
    )
    assert result.status == "succeeded"
    assert result.inserted == 2
    assert result.errors == 0


def test_changed_partner_is_persisted_once(db_session: Session) -> None:
    api = FakeAdvbox(_records(1))
    runner = _runner(db_session, api)
    asyncio.run(runner.run_resource("customers", batch_key="synthetic-link-base"))
    customer = db_session.scalar(select(Customer).where(Customer.advbox_id == 8_000_000))
    assert customer is not None
    partner = synthetic_partner(external_id="SYNTHETIC-SYNC-PARTNER")
    db_session.add(partner)
    db_session.flush()
    db_session.add(
        PartnerCaseLink(
            partner_id=partner.id,
            advbox_entity_type="customer",
            advbox_entity_id=customer.advbox_id,
            customer_id=customer.id,
            valid_from=date(2026, 1, 1),
            source="admin",
            status="active",
        )
    )
    db_session.flush()
    api.records[0]["name"] = "Synthetic Changed Customer"
    result = asyncio.run(runner.run_resource("customers", batch_key="synthetic-changed"))
    assert result.updated == 1
    assert result.changed_partners == 1
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(SyncChangedPartner)
            .where(SyncChangedPartner.partner_id == partner.id)
        )
        == 1
    )


def test_dry_run_does_not_write(db_session: Session) -> None:
    api = FakeAdvbox(_records(2))
    result = asyncio.run(
        _runner(db_session, api).run_resource("customers", batch_key="dry", dry_run=True)
    )
    assert result.fetched == 2
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(SyncRun)
            .where(SyncRun.idempotency_key == "dry:customers")
        )
        == 0
    )


def test_lawsuit_relationship_and_financial_amount_are_idempotent(db_session: Session) -> None:
    class PortfolioApi:
        async def list_page(self, resource: str, *, limit: int, offset: int) -> SimpleNamespace:
            records: dict[str, list[dict[str, object]]] = {
                "customers": [{"id": 7_000_001, "name": "Synthetic Portfolio Customer"}],
                "lawsuits": [
                    {
                        "id": 7_100_001,
                        "customers": [{"customer_id": 7_000_001}],
                        "process_date": "2026-01-01",
                    }
                ],
                "transactions": [
                    {
                        "id": 7_200_001,
                        "lawsuit_id": 7_100_001,
                        "amount": Decimal("0.00"),
                        "date_due": "2026-02-01",
                    }
                ],
                "last_movements": [
                    {
                        "lawsuit_id": 7_100_001,
                        "date": "2026-02-03 12:00:00",
                        "title": "Synthetic Movement",
                    }
                ],
            }
            return SimpleNamespace(
                payload={
                    "data": records[resource][offset : offset + limit],
                    "totalCount": len(records[resource]),
                    "limit": limit,
                    "offset": offset,
                }
            )

    runner = _runner(db_session, PortfolioApi())  # type: ignore[arg-type]
    for batch in ("synthetic-portfolio-1", "synthetic-portfolio-2"):
        for resource in ("customers", "lawsuits", "transactions", "last_movements"):
            result = asyncio.run(runner.run_resource(resource, batch_key=batch))
            assert result.status == "succeeded"
            assert result.inserted == (1 if batch.endswith("-1") else 0)

    customer = db_session.scalar(select(Customer).where(Customer.advbox_id == 7_000_001))
    lawsuit = db_session.scalar(select(Lawsuit).where(Lawsuit.advbox_id == 7_100_001))
    transaction = db_session.scalar(
        select(FinancialTransaction).where(FinancialTransaction.advbox_id == 7_200_001)
    )
    assert customer is not None and lawsuit is not None and transaction is not None
    assert transaction.amount == Decimal("0.00")
    assert transaction.amount_status == "available"
    assert transaction.lawsuit_id == lawsuit.id
    assert (
        db_session.scalar(
            select(func.count()).select_from(Movement).where(Movement.lawsuit_id == lawsuit.id)
        )
        == 1
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(LawsuitCustomer)
            .where(
                LawsuitCustomer.customer_id == customer.id,
                LawsuitCustomer.lawsuit_id == lawsuit.id,
            )
        )
        == 1
    )

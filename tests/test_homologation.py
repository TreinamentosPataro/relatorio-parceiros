"""Count-only homologation tests with synthetic API records."""

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from partner_reports.jobs.homologation import (
    HomologationDryRun,
    MappingReference,
)


class FakeClient:
    def __init__(self) -> None:
        self.records = {
            "customers": [{"id": 1}, {"id": 2}],
            "lawsuits": [
                {"id": 10, "customers": [{"customer_id": 1}]},
                {
                    "id": 11,
                    "process_number": "SYNTHETIC-11",
                    "customers": [{"customer_id": 1}, {"customer_id": 2}],
                },
                {"id": 12, "customers": []},
            ],
            "transactions": [
                {"id": 20, "lawsuit_id": 10, "amount": Decimal("0.00")},
                {"id": 21, "lawsuit_id": 10, "amount": Decimal("10.00")},
                {"id": 22, "lawsuit_id": 999, "amount": None},
            ],
            "last_movements": [
                {"lawsuit_id": 10, "date": "2026-09-10T12:00:00-03:00", "title": "Synthetic"},
                {"lawsuit_id": 11, "date": "2026-01-01T12:00:00-03:00", "title": "Synthetic"},
            ],
        }

    async def list_page(self, resource: str, *, limit: int, offset: int) -> SimpleNamespace:
        rows = self.records[resource]
        return SimpleNamespace(
            payload={
                "data": rows[offset : offset + limit],
                "totalCount": len(rows),
                "limit": limit,
                "offset": offset,
            }
        )


def test_full_dry_run_returns_only_counts_and_technical_quality() -> None:
    snapshot = asyncio.run(HomologationDryRun(FakeClient()).run())  # type: ignore[arg-type]
    summary = snapshot.public_summary(
        partner_keys={"partner-a", "partner-b"},
        mappings=(
            MappingReference("customer", 1, "partner-a"),
            MappingReference("lawsuit", 12, "partner-a"),
            MappingReference("customer", 2, "partner-b"),
        ),
        as_of=date(2026, 9, 21),
    )

    assert summary["lawsuits"] == {
        "linked": 2,
        "unlinked": 0,
        "conflicts": 1,
        "missing_process_number": 2,
        "customers_with_multiple_processes": 1,
        "mapping_references_not_found": 0,
    }
    assert summary["partners"] == {"total": 2, "with_processes": 1, "without_processes": 1}
    assert summary["financial"] == {
        "records_available": 2,
        "records_not_provided": 1,
        "orphan_records": 1,
        "lawsuits_with_records": 1,
        "lawsuits_without_records": 2,
        "lawsuits_with_multiple_records": 1,
        "approved_business_rule": False,
    }
    assert summary["last_movement_age"]["0_30_days"] == 1
    assert summary["last_movement_age"]["181_365_days"] == 1
    assert summary["last_movement_age"]["without_movement"] == 1
    assert all(item["rejected"] == 0 for item in summary["resources"].values())


def test_rejected_and_duplicate_records_are_counted_without_values() -> None:
    client = FakeClient()
    client.records["customers"] = [{"id": 1}, {"id": 1}, {"id": "invalid"}]
    snapshot = asyncio.run(HomologationDryRun(client).run())  # type: ignore[arg-type]
    quality = snapshot.public_summary(partner_keys=set(), mappings=(), as_of=date(2026, 9, 21))

    assert quality["resources"]["customers"] == {
        "pages": 1,
        "total_reported": 3,
        "accepted": 1,
        "rejected": 2,
        "duplicate_ids": 1,
    }
    assert "invalid" not in str(quality)

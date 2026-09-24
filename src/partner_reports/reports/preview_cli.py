"""Generate 0/1/many-case previews from deliberately synthetic snapshots only."""

import argparse
import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from partner_reports.domain.report_view import (
    PortfolioSnapshot,
    SnapshotCase,
    SnapshotCustomer,
    SnapshotLink,
    SnapshotMovement,
    build_internal_report,
)
from partner_reports.reports.render import generate_pdf, render_html

_AS_OF = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
_PARTNER_ID = uuid.UUID(int=9000)


def synthetic_preview(
    scenario: str,
    *,
    partner_id: uuid.UUID = _PARTNER_ID,
    partner_code: str | None = None,
    as_of: datetime = _AS_OF,
    report_version: int = 1,
):
    """Keep sample construction isolated from all real data and integrations."""

    counts = {"zero": (0, 0), "one": (1, 1), "many": (30, 55)}
    if scenario not in counts:
        raise ValueError("cenário sintético desconhecido")
    customer_count, case_count = counts[scenario]
    customers = tuple(SnapshotCustomer(uuid.UUID(int=1000 + i)) for i in range(customer_count))
    cases = tuple(
        SnapshotCase(uuid.UUID(int=2000 + i), (customers[i % customer_count].id,))
        for i in range(case_count)
    )
    links = tuple(
        SnapshotLink(
            partner_id=partner_id,
            entity_type="customer",
            entity_id=customer.id,
            valid_from=date(2026, 1, 1),
        )
        for customer in customers
    )
    movements = tuple(
        SnapshotMovement(case.id, as_of - timedelta(days=(index % 19) + 1))
        for index, case in enumerate(cases)
        if index % 7 != 0
    )
    snapshot = PortfolioSnapshot(
        partner_id=partner_id,
        partner_code=partner_code or f"SYNTHETIC-{scenario.upper()}",
        customers=customers,
        cases=cases,
        links=links,
        movements=movements,
        source_complete=True,
        linkage_approved=True,
        source_synced_at=as_of,
        linkage_validated_at=as_of,
    )
    return build_internal_report(
        snapshot,
        as_of=as_of,
        period_start=as_of.date().replace(day=1),
        generated_at=as_of + timedelta(minutes=1),
        report_version=report_version,
    )


async def _generate(output_root: Path, scenarios: list[str], executable_path: str | None) -> None:
    html_dir = output_root / "html"
    pdf_dir = output_root / "pdf"
    html_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    for scenario in scenarios:
        internal = synthetic_preview(scenario)
        (html_dir / f"preview_{scenario}.html").write_text(render_html(internal), encoding="utf-8")
        pdf = await generate_pdf(internal, executable_path=executable_path)
        (pdf_dir / f"preview_{scenario}.pdf").write_bytes(pdf)
        print(f"preview_{scenario}: HTML e PDF sintéticos gerados")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gerar prévias sintéticas HTML/PDF")
    parser.add_argument("--scenario", choices=("zero", "one", "many"), action="append")
    parser.add_argument("--output-root", type=Path, default=Path("output"))
    parser.add_argument("--chromium-executable", default=None)
    args = parser.parse_args()
    asyncio.run(
        _generate(
            args.output_root, args.scenario or ["zero", "one", "many"], args.chromium_executable
        )
    )


if __name__ == "__main__":
    main()

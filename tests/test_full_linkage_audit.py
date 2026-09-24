"""Synthetic full-list audit test that proves only aggregate values survive."""

import asyncio
from typing import Any

from partner_reports.integrations.advbox.client import SafeHttpResult
from partner_reports.integrations.advbox.linkage_audit import FullPortfolioLinkageAuditor
from partner_reports.integrations.advbox.linkage_report import render_full_linkage_audit


class SyntheticClient:
    async def get(
        self,
        endpoint: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> SafeHttpResult:
        del params
        if endpoint == "/customers":
            payload: Any = {
                "totalCount": 2,
                "data": [
                    {"id": 10, "origin": "SYNTHETIC_ORIGIN_ALPHA"},
                    {"id": 20, "origin": None},
                ],
            }
        else:
            payload = {
                "totalCount": 2,
                "data": [
                    {
                        "id": 100,
                        "folder": "SYNTHETIC_FOLDER_PRIVATE",
                        "responsible_id": 7,
                        "customers": [{"customer_id": 10, "origin": "SYNTHETIC_ORIGIN_ALPHA"}],
                    },
                    {
                        "id": 200,
                        "customers": [
                            {"customer_id": 20, "origin": "SYNTHETIC_ORIGIN_BETA"},
                            {"customer_id": 30, "origin": "SYNTHETIC_ORIGIN_GAMMA"},
                        ],
                    },
                ],
            }
        return SafeHttpResult(status_code=200, duration_ms=1, payload=payload)


def test_full_scan_outputs_counts_only() -> None:
    result = asyncio.run(
        FullPortfolioLinkageAuditor(SyntheticClient()).run()  # type: ignore[arg-type]
    )

    assert result.customers.total == 2
    assert result.customers.with_origin == 1
    assert result.lawsuits.total == 2
    assert result.lawsuits.with_one_customer_origin == 1
    assert result.lawsuits.with_multiple_customer_origins == 1
    assert result.lawsuit_customer_references == 3
    assert result.lawsuit_customer_references_missing == 1
    assert result.validation_without_mapping.lawsuits.unlinked == 2

    rendered = render_full_linkage_audit(result)
    assert "SYNTHETIC_ORIGIN_ALPHA" not in rendered
    assert "SYNTHETIC_FOLDER_PRIVATE" not in rendered

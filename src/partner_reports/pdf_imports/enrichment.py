"""GET-only report data for the reconciled lawsuits of one portfolio (ADR-007).

Movements and entries are read per portfolio lawsuit (`/movements/{id}` and the
documented `lawsuit_id` filter of `/transactions`); a record of any other lawsuit
aborts the read. Financial entries are limited to the accounting categories.
"""

from collections.abc import Collection
from dataclasses import dataclass, field

from pydantic import ValidationError

from partner_reports.contracts.ingestion import AdvboxMovementInput, AdvboxTransactionInput
from partner_reports.integrations.advbox.client import (
    MAX_PAGE_SIZE,
    AdvboxClient,
    AdvboxUnexpectedResponse,
)
from partner_reports.integrations.advbox.normalize import normalize_record
from partner_reports.jobs.sync import _page
from partner_reports.reports.financial import classify_entry

MAX_TRANSACTIONS = 200_000


@dataclass(frozen=True)
class PortfolioEnrichment:
    last_movements: dict[int, AdvboxMovementInput | None] = field(repr=False)
    transactions: tuple[AdvboxTransactionInput, ...] = field(repr=False)


def _latest_movement(payload: object, lawsuit_id: int) -> AdvboxMovementInput | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise AdvboxUnexpectedResponse("andamentos sem lista válida")
    latest: AdvboxMovementInput | None = None
    for raw in payload["data"]:
        if not isinstance(raw, dict):
            raise AdvboxUnexpectedResponse("andamento inválido")
        try:
            movement = normalize_record("last_movements", raw)
        except (AdvboxUnexpectedResponse, ValidationError):
            raise AdvboxUnexpectedResponse("andamento fora do contrato técnico") from None
        if movement.lawsuit_external_id != lawsuit_id:
            raise AdvboxUnexpectedResponse("andamento de outro processo")
        if latest is None or movement.occurred_at > latest.occurred_at:
            latest = movement
    return latest


async def collect_portfolio_enrichment(
    client: AdvboxClient, lawsuit_ids: Collection[int]
) -> PortfolioEnrichment:
    wanted = set(lawsuit_ids)
    movements = {
        lawsuit_id: _latest_movement(
            (await client.lawsuit_movements(lawsuit_id)).payload, lawsuit_id
        )
        for lawsuit_id in sorted(wanted)
    }
    kept: dict[int, AdvboxTransactionInput] = {}
    for lawsuit_id in sorted(wanted):
        offset = 0
        expected_total: int | None = None
        while expected_total is None or offset < expected_total:
            response = await client.lawsuit_transactions_page(
                lawsuit_id, limit=MAX_PAGE_SIZE, offset=offset
            )
            records, total = _page(
                response.payload, requested_offset=offset, requested_limit=MAX_PAGE_SIZE
            )
            if expected_total is not None and total != expected_total:
                raise AdvboxUnexpectedResponse("totalCount de lançamentos mudou durante a leitura")
            if total > MAX_TRANSACTIONS:
                raise AdvboxUnexpectedResponse("lançamentos excedem o limite técnico")
            expected_total = total
            for raw in records:
                # Fail closed if the filter was not applied: another lawsuit never enters.
                if raw.get("lawsuit_id") != lawsuit_id:
                    raise AdvboxUnexpectedResponse("filtro por processo não aplicado")
                try:
                    entry = normalize_record("transactions", raw)
                except (AdvboxUnexpectedResponse, ValidationError):
                    raise AdvboxUnexpectedResponse("lançamento fora do contrato técnico") from None
                if classify_entry(entry.entry_type, entry.category) is None:
                    continue
                if entry.external_id in kept:
                    raise AdvboxUnexpectedResponse("lançamento duplicado na leitura")
                kept[entry.external_id] = entry
            offset += len(records)
    return PortfolioEnrichment(movements, tuple(kept[key] for key in sorted(kept)))

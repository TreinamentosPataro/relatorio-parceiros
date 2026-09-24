"""Count-only full dry-run for homologation; raw API values are never persisted."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from pydantic import ValidationError

from partner_reports.contracts.ingestion import (
    AdvboxCustomerInput,
    AdvboxLawsuitInput,
    AdvboxMovementInput,
    AdvboxTransactionInput,
)
from partner_reports.integrations.advbox.client import AdvboxClient, AdvboxUnexpectedResponse
from partner_reports.integrations.advbox.normalize import normalize_record
from partner_reports.jobs.sync import PAGE_SIZE, RESOURCES, _page


@dataclass(frozen=True)
class MappingReference:
    entity_type: str
    entity_id: int
    partner_key: str


@dataclass
class ResourceQuality:
    pages: int = 0
    total_reported: int | None = None
    accepted: int = 0
    rejected: int = 0
    duplicate_ids: int = 0


@dataclass
class QualitySnapshot:
    resources: dict[str, ResourceQuality] = field(
        default_factory=lambda: {resource: ResourceQuality() for resource in RESOURCES}
    )
    customer_ids: set[int] = field(default_factory=set, repr=False)
    lawsuit_customers: dict[int, tuple[int, ...]] = field(default_factory=dict, repr=False)
    lawsuit_without_number: int = 0
    transaction_ids: set[int] = field(default_factory=set, repr=False)
    transactions_by_lawsuit: Counter[int] = field(default_factory=Counter, repr=False)
    transactions_without_lawsuit: int = 0
    financial_available: int = 0
    financial_not_provided: int = 0
    movement_fingerprints: set[str] = field(default_factory=set, repr=False)
    latest_movement: dict[int, datetime] = field(default_factory=dict, repr=False)

    def accept(self, resource: str, item: Any) -> None:
        quality = self.resources[resource]
        if isinstance(item, AdvboxCustomerInput):
            if item.external_id in self.customer_ids:
                quality.duplicate_ids += 1
                quality.rejected += 1
                return
            self.customer_ids.add(item.external_id)
        elif isinstance(item, AdvboxLawsuitInput):
            if item.external_id in self.lawsuit_customers:
                quality.duplicate_ids += 1
                quality.rejected += 1
                return
            self.lawsuit_customers[item.external_id] = item.customer_external_ids
            self.lawsuit_without_number += item.process_number is None
        elif isinstance(item, AdvboxTransactionInput):
            if item.external_id in self.transaction_ids:
                quality.duplicate_ids += 1
                quality.rejected += 1
                return
            self.transaction_ids.add(item.external_id)
            if item.lawsuit_external_id is None:
                self.transactions_without_lawsuit += 1
            else:
                self.transactions_by_lawsuit[item.lawsuit_external_id] += 1
            if item.amount is None:
                self.financial_not_provided += 1
            else:
                self.financial_available += 1
        elif isinstance(item, AdvboxMovementInput):
            if item.source_fingerprint in self.movement_fingerprints:
                quality.duplicate_ids += 1
                quality.rejected += 1
                return
            self.movement_fingerprints.add(item.source_fingerprint)
            previous = self.latest_movement.get(item.lawsuit_external_id)
            if previous is None or item.occurred_at > previous:
                self.latest_movement[item.lawsuit_external_id] = item.occurred_at
        else:  # pragma: no cover - normalize_record is the closed dispatch
            raise TypeError("tipo normalizado desconhecido")
        quality.accepted += 1

    def public_summary(
        self,
        *,
        partner_keys: set[str],
        mappings: tuple[MappingReference, ...],
        as_of: date,
    ) -> dict[str, Any]:
        customer_partners: dict[int, set[str]] = defaultdict(set)
        lawsuit_partners: dict[int, set[str]] = defaultdict(set)
        nonexistent_mapping_references = 0
        for mapping in mappings:
            exists = (
                mapping.entity_id in self.customer_ids
                if mapping.entity_type == "customer"
                else mapping.entity_id in self.lawsuit_customers
            )
            if not exists:
                nonexistent_mapping_references += 1
                continue
            target = customer_partners if mapping.entity_type == "customer" else lawsuit_partners
            target[mapping.entity_id].add(mapping.partner_key)

        linked = unlinked = conflicts = 0
        processes_by_partner: Counter[str] = Counter()
        customers_with_multiple_processes = Counter(
            customer_id
            for customer_ids in self.lawsuit_customers.values()
            for customer_id in customer_ids
        )
        for lawsuit_id, customer_ids in self.lawsuit_customers.items():
            candidates = set(lawsuit_partners[lawsuit_id])
            for customer_id in customer_ids:
                candidates.update(customer_partners[customer_id])
            if not candidates:
                unlinked += 1
            elif len(candidates) > 1:
                conflicts += 1
            else:
                linked += 1
                processes_by_partner[next(iter(candidates))] += 1

        lawsuit_ids = set(self.lawsuit_customers)
        financial_orphans = self.transactions_without_lawsuit + sum(
            count
            for lawsuit_id, count in self.transactions_by_lawsuit.items()
            if lawsuit_id not in lawsuit_ids
        )
        lawsuits_with_financial = len(lawsuit_ids & self.transactions_by_lawsuit.keys())
        lawsuits_with_installments = sum(
            count > 1
            for lawsuit_id, count in self.transactions_by_lawsuit.items()
            if lawsuit_id in lawsuit_ids
        )
        ages = Counter()
        future_movements = 0
        for lawsuit_id in lawsuit_ids:
            movement = self.latest_movement.get(lawsuit_id)
            if movement is None:
                ages["sem_andamento"] += 1
                continue
            days = (as_of - movement.date()).days
            if days < 0:
                future_movements += 1
            elif days <= 30:
                ages["0_30_dias"] += 1
            elif days <= 90:
                ages["31_90_dias"] += 1
            elif days <= 180:
                ages["91_180_dias"] += 1
            elif days <= 365:
                ages["181_365_dias"] += 1
            else:
                ages["mais_365_dias"] += 1

        return {
            "resources": {
                resource: {
                    "pages": quality.pages,
                    "total_reported": quality.total_reported,
                    "accepted": quality.accepted,
                    "rejected": quality.rejected,
                    "duplicate_ids": quality.duplicate_ids,
                }
                for resource, quality in self.resources.items()
            },
            "partners": {
                "total": len(partner_keys),
                "with_processes": sum(processes_by_partner[key] > 0 for key in partner_keys),
                "without_processes": sum(processes_by_partner[key] == 0 for key in partner_keys),
            },
            "lawsuits": {
                "linked": linked,
                "unlinked": unlinked,
                "conflicts": conflicts,
                "missing_process_number": self.lawsuit_without_number,
                "customers_with_multiple_processes": sum(
                    count > 1 for count in customers_with_multiple_processes.values()
                ),
                "mapping_references_not_found": nonexistent_mapping_references,
            },
            "financial": {
                "records_available": self.financial_available,
                "records_not_provided": self.financial_not_provided,
                "orphan_records": financial_orphans,
                "lawsuits_with_records": lawsuits_with_financial,
                "lawsuits_without_records": len(lawsuit_ids) - lawsuits_with_financial,
                "lawsuits_with_multiple_records": lawsuits_with_installments,
                "approved_business_rule": False,
            },
            "last_movement_age": {
                "0_30_days": ages["0_30_dias"],
                "31_90_days": ages["31_90_dias"],
                "91_180_days": ages["91_180_dias"],
                "181_365_days": ages["181_365_dias"],
                "over_365_days": ages["mais_365_dias"],
                "without_movement": ages["sem_andamento"],
                "future_dated": future_movements,
            },
        }


class HomologationDryRun:
    """Scan every confirmed global endpoint and retain only technical/count projections."""

    def __init__(self, client: AdvboxClient) -> None:
        self.client = client

    async def run(self) -> QualitySnapshot:
        snapshot = QualitySnapshot()
        for resource in RESOURCES:
            await self._scan_resource(resource, snapshot)
        return snapshot

    async def _scan_resource(self, resource: str, snapshot: QualitySnapshot) -> None:
        offset = 0
        expected_total: int | None = None
        quality = snapshot.resources[resource]
        while expected_total is None or offset < expected_total:
            response = await self.client.list_page(resource, limit=PAGE_SIZE, offset=offset)
            records, total = _page(
                response.payload, requested_offset=offset, requested_limit=PAGE_SIZE
            )
            if expected_total is not None and total != expected_total:
                raise AdvboxUnexpectedResponse("totalCount mudou durante o dry-run integral")
            expected_total = total
            quality.total_reported = total
            quality.pages += 1
            for record in records:
                try:
                    snapshot.accept(resource, normalize_record(resource, record))
                except (AdvboxUnexpectedResponse, ValidationError):
                    quality.rejected += 1
            offset += len(records)

        if quality.accepted + quality.rejected != expected_total:
            raise AdvboxUnexpectedResponse("contagem validada diverge do total informado")

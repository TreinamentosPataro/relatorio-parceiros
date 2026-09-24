"""Full, read-only portfolio scan that retains only opaque IDs and aggregate counts."""

import hashlib
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from partner_reports.domain.partner_linkage import (
    LawsuitReference,
    LinkageValidationResult,
    validate_partner_linkage,
)
from partner_reports.integrations.advbox.client import (
    AdvboxAuditClient,
    AdvboxUnexpectedResponse,
)


@dataclass(frozen=True)
class CandidateCoverage:
    """Sanitized coverage facts for one complete API collection."""

    total: int
    pages: int
    duplicate_ids: int
    direct_partner_fields: int
    with_origin: int
    without_origin: int
    distinct_origins: int
    with_folder: int = 0
    with_responsible_id: int = 0
    with_one_customer_origin: int = 0
    with_multiple_customer_origins: int = 0


@dataclass(frozen=True)
class FullPortfolioLinkageAudit:
    """Safe aggregate produced after scanning all available customers and lawsuits."""

    started_at: datetime
    finished_at: datetime
    customers: CandidateCoverage
    lawsuits: CandidateCoverage
    lawsuit_customer_references: int
    lawsuit_customer_references_missing: int
    validation_without_mapping: LinkageValidationResult
    _customer_ids: frozenset[str] = field(repr=False)
    _lawsuits: tuple[LawsuitReference, ...] = field(repr=False)


def _opaque_digest(value: Any, salt: bytes) -> bytes | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().casefold().encode("utf-8")
    return hashlib.sha256(salt + normalized).digest()


def _technical_id(value: Any) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _contains_direct_partner_field(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in {
                "partner_id",
                "partnerid",
                "parceiro_id",
                "parceiroid",
            }:
                return True
            if (
                normalized in {"partner", "parceiro"}
                and isinstance(nested, Mapping)
                and "id" in nested
            ):
                return True
            if _contains_direct_partner_field(nested):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_direct_partner_field(item) for item in value)
    return False


def _page(payload: Any) -> tuple[list[Mapping[str, Any]], int]:
    if not isinstance(payload, Mapping):
        raise AdvboxUnexpectedResponse("coleção paginada não retornou objeto JSON")
    data = payload.get("data")
    total = payload.get("totalCount")
    if not isinstance(data, list) or not isinstance(total, int):
        raise AdvboxUnexpectedResponse("coleção sem data/totalCount válidos")
    if not all(isinstance(item, Mapping) for item in data):
        raise AdvboxUnexpectedResponse("coleção contém item estruturalmente inválido")
    return data, total


class FullPortfolioLinkageAuditor:
    """Scan both complete collections at the conservative audit rate."""

    _PAGE_SIZE = 100

    def __init__(self, client: AdvboxAuditClient) -> None:
        self._client = client
        self._salt = secrets.token_bytes(32)

    async def run(self) -> FullPortfolioLinkageAudit:
        started_at = datetime.now(UTC)
        customer_coverage, customer_ids = await self._scan_customers()
        lawsuit_coverage, lawsuits, relationship_count = await self._scan_lawsuits()
        referenced_customer_ids = {
            customer_id for lawsuit in lawsuits for customer_id in lawsuit.customer_ids
        }
        missing_relationships = len(referenced_customer_ids - customer_ids)
        validation = validate_partner_linkage(
            customer_ids=customer_ids,
            lawsuits=lawsuits,
            mappings=(),
            reference_date=date.today(),
        )
        return FullPortfolioLinkageAudit(
            started_at=started_at,
            finished_at=datetime.now(UTC),
            customers=customer_coverage,
            lawsuits=lawsuit_coverage,
            lawsuit_customer_references=relationship_count,
            lawsuit_customer_references_missing=missing_relationships,
            validation_without_mapping=validation,
            _customer_ids=frozenset(customer_ids),
            _lawsuits=lawsuits,
        )

    async def _scan_customers(self) -> tuple[CandidateCoverage, set[str]]:
        offset = 0
        expected_total: int | None = None
        pages = 0
        ids: set[str] = set()
        duplicate_ids = 0
        direct_fields = 0
        with_origin = 0
        origin_digests: set[bytes] = set()

        while expected_total is None or offset < expected_total:
            result = await self._client.get(
                "/customers",
                params={"limit": self._PAGE_SIZE, "offset": offset},
            )
            records, total = _page(result.payload)
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise AdvboxUnexpectedResponse("totalCount de customers mudou durante a leitura")
            pages += 1
            for record in records:
                identifier = _technical_id(record.get("id"))
                if identifier is None:
                    raise AdvboxUnexpectedResponse("customer sem identificador técnico")
                if identifier in ids:
                    duplicate_ids += 1
                ids.add(identifier)
                direct_fields += _contains_direct_partner_field(record)
                origin_digest = _opaque_digest(record.get("origin"), self._salt)
                if origin_digest is not None:
                    with_origin += 1
                    origin_digests.add(origin_digest)
            if not records and offset < expected_total:
                raise AdvboxUnexpectedResponse(
                    "paginação de customers terminou antes do totalCount"
                )
            offset += len(records)

        total_records = len(ids) + duplicate_ids
        return (
            CandidateCoverage(
                total=total_records,
                pages=pages,
                duplicate_ids=duplicate_ids,
                direct_partner_fields=direct_fields,
                with_origin=with_origin,
                without_origin=total_records - with_origin,
                distinct_origins=len(origin_digests),
            ),
            ids,
        )

    async def _scan_lawsuits(
        self,
    ) -> tuple[CandidateCoverage, tuple[LawsuitReference, ...], int]:
        offset = 0
        expected_total: int | None = None
        pages = 0
        ids: set[str] = set()
        duplicate_ids = 0
        direct_fields = 0
        with_origin = 0
        with_folder = 0
        with_responsible_id = 0
        with_one_origin = 0
        with_multiple_origins = 0
        origin_digests: set[bytes] = set()
        lawsuits: list[LawsuitReference] = []
        relationship_count = 0

        while expected_total is None or offset < expected_total:
            result = await self._client.get(
                "/lawsuits",
                params={"limit": self._PAGE_SIZE, "offset": offset},
            )
            records, total = _page(result.payload)
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise AdvboxUnexpectedResponse("totalCount de lawsuits mudou durante a leitura")
            pages += 1
            for record in records:
                identifier = _technical_id(record.get("id"))
                if identifier is None:
                    raise AdvboxUnexpectedResponse("lawsuit sem identificador técnico")
                if identifier in ids:
                    duplicate_ids += 1
                ids.add(identifier)
                direct_fields += _contains_direct_partner_field(record)
                with_folder += bool(
                    isinstance(record.get("folder"), str) and record["folder"].strip()
                )
                with_responsible_id += _technical_id(record.get("responsible_id")) is not None

                customer_ids: list[str] = []
                record_origins: set[bytes] = set()
                customers = record.get("customers")
                if isinstance(customers, list):
                    for customer in customers:
                        if not isinstance(customer, Mapping):
                            continue
                        customer_id = _technical_id(customer.get("customer_id"))
                        if customer_id is not None:
                            customer_ids.append(customer_id)
                            relationship_count += 1
                        origin_digest = _opaque_digest(customer.get("origin"), self._salt)
                        if origin_digest is not None:
                            record_origins.add(origin_digest)
                            origin_digests.add(origin_digest)
                if record_origins:
                    with_origin += 1
                if len(record_origins) == 1:
                    with_one_origin += 1
                elif len(record_origins) > 1:
                    with_multiple_origins += 1
                lawsuits.append(LawsuitReference(identifier, tuple(customer_ids)))
            if not records and offset < expected_total:
                raise AdvboxUnexpectedResponse("paginação de lawsuits terminou antes do totalCount")
            offset += len(records)

        total_records = len(ids) + duplicate_ids
        return (
            CandidateCoverage(
                total=total_records,
                pages=pages,
                duplicate_ids=duplicate_ids,
                direct_partner_fields=direct_fields,
                with_origin=with_origin,
                without_origin=total_records - with_origin,
                distinct_origins=len(origin_digests),
                with_folder=with_folder,
                with_responsible_id=with_responsible_id,
                with_one_customer_origin=with_one_origin,
                with_multiple_customer_origins=with_multiple_origins,
            ),
            tuple(lawsuits),
            relationship_count,
        )

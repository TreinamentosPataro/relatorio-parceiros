"""GET-only API snapshot and exact, name-free PDF manifest reconciliation."""

import hashlib
import json
import uuid
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import ValidationError

from partner_reports.contracts.ingestion import AdvboxLawsuitInput
from partner_reports.integrations.advbox.client import (
    MAX_PAGE_SIZE,
    AdvboxClient,
    AdvboxSourceChanged,
    AdvboxUnexpectedResponse,
)
from partner_reports.integrations.advbox.normalize import normalize_record, report_hash
from partner_reports.jobs.sync import PAGE_SIZE, _page
from partner_reports.pdf_imports.identifiers import normalize_folder, normalize_process_number
from partner_reports.pdf_imports.parser import ManifestItem

MAX_SNAPSHOT_ITEMS = 100_000
# Large pages cut a full lawsuit read from ~44 to ~5 requests at 20 GET/min.
SNAPSHOT_PAGE_SIZE = MAX_PAGE_SIZE


class MatchStatus(StrEnum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    AMBIGUOUS = "ambiguous"
    DUPLICATE_SOURCE = "duplicate_source"
    INVALID_IDENTIFIER = "invalid_identifier"


class MatchMethod(StrEnum):
    PROCESS_NUMBER_EXACT = "process_number_exact"
    FOLDER_EXACT_UNIQUE = "folder_exact_unique"


@dataclass(frozen=True)
class ApiCandidate:
    external_id: int
    process_number_normalized: str | None = field(repr=False)
    folder_exact: str | None = field(repr=False)
    record_digest: str = field(repr=False)
    customer_external_ids: tuple[int, ...] = field(default=(), repr=False)
    # In memory only; persisted solely for reconciled lawsuits (ADR-007).
    detail: AdvboxLawsuitInput | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class ScanCheckpoint:
    """Restartable in-memory page checkpoint; only technical projections are retained."""

    next_offset: int = 0
    expected_total: int | None = None
    candidates: tuple[ApiCandidate, ...] = field(default=(), repr=False)

    @property
    def complete(self) -> bool:
        return self.expected_total is not None and self.next_offset == self.expected_total


@dataclass(frozen=True)
class ApiSnapshot:
    sha256: str
    total: int
    verified_at: datetime
    candidates: tuple[ApiCandidate, ...] = field(repr=False)


@dataclass(frozen=True)
class MatchResult:
    manifest_item_id: uuid.UUID = field(repr=False)
    status: MatchStatus
    method: MatchMethod | None
    matched_advbox_id: int | None = field(repr=False)
    reason_code: str | None


@dataclass(frozen=True)
class ReconciliationSummary:
    total: int
    matched: int
    unmatched: int
    ambiguous: int
    duplicate_source: int
    invalid_identifier: int


@dataclass(frozen=True)
class EnrichmentCoverage:
    """Count-only official endpoint coverage; no content or names are returned."""

    referenced_customers: int
    customers_found: int
    transactions_found: int
    last_movements_found: int


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _identifiers_only(raw: dict) -> ApiCandidate:
    """Keep a lawsuit with a malformed descriptive field matchable, without its details.

    The read covers every lawsuit of the office; one record edited with an unexpected
    value must not block reports for portfolios that do not even contain it.
    """
    external_id = raw.get("id")
    if not isinstance(external_id, int) or isinstance(external_id, bool) or external_id <= 0:
        raise AdvboxUnexpectedResponse("processo sem ID técnico válido")
    related = raw.get("customers")
    customer_ids = tuple(
        sorted(
            {
                customer["customer_id"]
                for customer in (related if isinstance(related, list) else [])
                if isinstance(customer, Mapping)
                and isinstance(customer.get("customer_id"), int)
                and not isinstance(customer.get("customer_id"), bool)
                and customer["customer_id"] > 0
            }
        )
    )
    encoded = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)
    return ApiCandidate(
        external_id=external_id,
        process_number_normalized=normalize_process_number(
            _optional_text(raw.get("process_number"))
        ),
        folder_exact=normalize_folder(_optional_text(raw.get("folder"))),
        record_digest=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        customer_external_ids=customer_ids,
    )


def _project_lawsuit(raw: dict) -> ApiCandidate:
    try:
        normalized = normalize_record("lawsuits", raw)
    except (AdvboxUnexpectedResponse, ValidationError):
        return _identifiers_only(raw)
    return ApiCandidate(
        external_id=normalized.external_id,
        process_number_normalized=normalize_process_number(normalized.process_number),
        folder_exact=normalize_folder(normalized.folder),
        record_digest=report_hash(normalized),
        customer_external_ids=normalized.customer_external_ids,
        detail=normalized,
    )


async def advance_scan(client: AdvboxClient, checkpoint: ScanCheckpoint) -> ScanCheckpoint:
    """Read one page. On transport failure the caller retains the prior checkpoint."""
    if checkpoint.complete:
        return checkpoint
    if checkpoint.next_offset != len(checkpoint.candidates):
        raise ValueError("checkpoint técnico inconsistente")
    response = await client.list_page(
        "lawsuits", limit=SNAPSHOT_PAGE_SIZE, offset=checkpoint.next_offset
    )
    records, total = _page(
        response.payload,
        requested_offset=checkpoint.next_offset,
        requested_limit=SNAPSHOT_PAGE_SIZE,
    )
    if checkpoint.expected_total is not None and total != checkpoint.expected_total:
        raise AdvboxSourceChanged("totalCount mudou durante a fotografia")
    if total > MAX_SNAPSHOT_ITEMS:
        raise AdvboxUnexpectedResponse("fotografia excede o limite técnico")
    projected = tuple(_project_lawsuit(raw) for raw in records)
    existing_ids = {candidate.external_id for candidate in checkpoint.candidates}
    new_ids = [candidate.external_id for candidate in projected]
    if len(new_ids) != len(set(new_ids)):
        raise AdvboxUnexpectedResponse("ID técnico duplicado na fotografia")
    if existing_ids.intersection(new_ids):
        # A lawsuit created or removed during the read shifts the offset pages.
        raise AdvboxSourceChanged("páginas deslocadas durante a fotografia")
    next_offset = checkpoint.next_offset + len(projected)
    if next_offset == total and len(checkpoint.candidates) + len(projected) != total:
        raise AdvboxSourceChanged("fotografia técnica incompleta")
    return ScanCheckpoint(next_offset, total, checkpoint.candidates + projected)


async def scan_to_end(
    client: AdvboxClient, checkpoint: ScanCheckpoint | None = None
) -> ScanCheckpoint:
    current = checkpoint or ScanCheckpoint()
    while not current.complete:
        current = await advance_scan(client, current)
    return current


def _snapshot_digest(candidates: tuple[ApiCandidate, ...]) -> str:
    rows = [
        [
            candidate.external_id,
            candidate.process_number_normalized,
            candidate.folder_exact,
            candidate.record_digest,
            candidate.customer_external_ids,
        ]
        for candidate in sorted(candidates, key=lambda candidate: candidate.external_id)
    ]
    encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def require_snapshot_integrity(snapshot: ApiSnapshot) -> None:
    if (
        snapshot.total != len(snapshot.candidates)
        or snapshot.sha256 != _snapshot_digest(snapshot.candidates)
        or len({item.external_id for item in snapshot.candidates}) != snapshot.total
    ):
        raise ValueError("fotografia técnica inconsistente")


@dataclass(frozen=True)
class RelevantKeys:
    """Manifest identifiers whose lawsuits must be stable across the two reads."""

    process_numbers: frozenset[str] = field(repr=False)
    folders: frozenset[str] = field(repr=False)

    @classmethod
    def from_manifest(cls, items: tuple[ManifestItem, ...]) -> "RelevantKeys":
        return cls(
            frozenset(
                item.process_number_normalized for item in items if item.process_number_normalized
            ),
            frozenset(item.folder_exact for item in items if item.folder_exact),
        )

    def select(self, candidates: tuple[ApiCandidate, ...]) -> tuple[ApiCandidate, ...]:
        return tuple(
            candidate
            for candidate in candidates
            if candidate.process_number_normalized in self.process_numbers
            or candidate.folder_exact in self.folders
        )


async def collect_verified_snapshot(
    client: AdvboxClient,
    checkpoint: ScanCheckpoint | None = None,
    *,
    relevant: RelevantKeys | None = None,
) -> ApiSnapshot:
    """Require two complete reads that agree; offset pagination is not an atomic snapshot.

    With `relevant`, only the lawsuits sharing a number or folder with the manifest must
    agree: other lawsuits edited by the office during the read do not affect the result.
    """
    first = await scan_to_end(client, checkpoint)
    second = await scan_to_end(client)
    if relevant is None:
        if first.expected_total != second.expected_total:
            raise AdvboxSourceChanged("totalCount mudou entre leituras")
        compared = (first.candidates, second.candidates)
    else:
        compared = (relevant.select(first.candidates), relevant.select(second.candidates))
    first_digest = _snapshot_digest(first.candidates)
    if _snapshot_digest(compared[0]) != _snapshot_digest(compared[1]):
        raise AdvboxSourceChanged("origem mudou entre leituras")
    return ApiSnapshot(first_digest, first.expected_total or 0, datetime.now(UTC), first.candidates)


def reconcile_items(
    items: tuple[ManifestItem, ...], snapshot: ApiSnapshot
) -> tuple[MatchResult, ...]:
    """Classify every source item exactly once using only number or folder."""
    by_number: dict[str, list[ApiCandidate]] = defaultdict(list)
    by_folder: dict[str, list[ApiCandidate]] = defaultdict(list)
    for candidate in snapshot.candidates:
        if candidate.process_number_normalized:
            by_number[candidate.process_number_normalized].append(candidate)
        if candidate.folder_exact:
            by_folder[candidate.folder_exact].append(candidate)

    results: list[MatchResult] = []
    source_keys = Counter(
        ("number", normalize_process_number(item.process_number_normalized))
        if item.process_number_normalized
        else ("folder", normalize_folder(item.folder_exact))
        for item in items
    )
    for item in items:
        flags = set(item.quality_flags)
        source_key = (
            ("number", normalize_process_number(item.process_number_normalized))
            if item.process_number_normalized
            else ("folder", normalize_folder(item.folder_exact))
        )
        if "duplicate_source" in flags or (source_key[1] and source_keys[source_key] > 1):
            results.append(
                MatchResult(
                    item.manifest_item_id,
                    MatchStatus.DUPLICATE_SOURCE,
                    None,
                    None,
                    "duplicate_source",
                )
            )
            continue
        if flags.intersection({"invalid_identifier", "missing_identifier", "incomplete_block"}):
            results.append(
                MatchResult(
                    item.manifest_item_id,
                    MatchStatus.INVALID_IDENTIFIER,
                    None,
                    None,
                    "invalid_identifier",
                )
            )
            continue
        number = normalize_process_number(item.process_number_normalized)
        folder = normalize_folder(item.folder_exact)
        if item.process_number_normalized and number is None or not number and not folder:
            results.append(
                MatchResult(
                    item.manifest_item_id,
                    MatchStatus.INVALID_IDENTIFIER,
                    None,
                    None,
                    "invalid_identifier",
                )
            )
            continue
        candidates = by_number[number] if number else by_folder[folder]
        method = MatchMethod.PROCESS_NUMBER_EXACT if number else MatchMethod.FOLDER_EXACT_UNIQUE
        if not candidates:
            results.append(
                MatchResult(
                    item.manifest_item_id, MatchStatus.UNMATCHED, None, None, "no_exact_candidate"
                )
            )
        elif len(candidates) > 1:
            results.append(
                MatchResult(
                    item.manifest_item_id,
                    MatchStatus.AMBIGUOUS,
                    None,
                    None,
                    "multiple_exact_candidates",
                )
            )
        elif number and folder and candidates[0].folder_exact not in (None, folder):
            results.append(
                MatchResult(
                    item.manifest_item_id,
                    MatchStatus.AMBIGUOUS,
                    None,
                    None,
                    "number_folder_conflict",
                )
            )
        else:
            results.append(
                MatchResult(
                    item.manifest_item_id,
                    MatchStatus.MATCHED,
                    method,
                    candidates[0].external_id,
                    None,
                )
            )

    matched_ids = Counter(
        result.matched_advbox_id for result in results if result.status is MatchStatus.MATCHED
    )
    return tuple(
        replace(
            result,
            status=MatchStatus.DUPLICATE_SOURCE,
            method=None,
            matched_advbox_id=None,
            reason_code="duplicate_target",
        )
        if result.status is MatchStatus.MATCHED and matched_ids[result.matched_advbox_id] > 1
        else result
        for result in results
    )


def summarize(results: tuple[MatchResult, ...]) -> ReconciliationSummary:
    counts = Counter(result.status for result in results)
    return ReconciliationSummary(
        total=len(results),
        matched=counts[MatchStatus.MATCHED],
        unmatched=counts[MatchStatus.UNMATCHED],
        ambiguous=counts[MatchStatus.AMBIGUOUS],
        duplicate_source=counts[MatchStatus.DUPLICATE_SOURCE],
        invalid_identifier=counts[MatchStatus.INVALID_IDENTIFIER],
    )


async def collect_official_enrichment_coverage(
    client: AdvboxClient,
    snapshot: ApiSnapshot,
    results: tuple[MatchResult, ...],
) -> EnrichmentCoverage:
    """Check related official collections at the shared GET limit; retain counts only."""
    matched_ids = {
        result.matched_advbox_id for result in results if result.status is MatchStatus.MATCHED
    }
    if not matched_ids:
        return EnrichmentCoverage(0, 0, 0, 0)
    by_id = {candidate.external_id: candidate for candidate in snapshot.candidates}
    customer_ids = {
        customer_id
        for lawsuit_id in matched_ids
        for customer_id in by_id[lawsuit_id].customer_external_ids
    }
    found_customers: set[int] = set()
    transaction_ids: set[int] = set()
    movement_count = 0
    for resource in ("customers", "transactions", "last_movements"):
        offset = 0
        expected_total: int | None = None
        while expected_total is None or offset < expected_total:
            response = await client.list_page(resource, limit=PAGE_SIZE, offset=offset)
            records, total = _page(
                response.payload, requested_offset=offset, requested_limit=PAGE_SIZE
            )
            if expected_total is not None and total != expected_total:
                raise AdvboxUnexpectedResponse("totalCount mudou no enriquecimento")
            expected_total = total
            for raw in records:
                try:
                    item = normalize_record(resource, raw)
                except (AdvboxUnexpectedResponse, ValidationError):
                    raise AdvboxUnexpectedResponse("recurso fora do contrato técnico") from None
                if resource == "customers" and item.external_id in customer_ids:
                    found_customers.add(item.external_id)
                elif resource == "transactions" and item.lawsuit_external_id in matched_ids:
                    if item.external_id in transaction_ids:
                        raise AdvboxUnexpectedResponse("transação técnica duplicada")
                    transaction_ids.add(item.external_id)
                elif resource == "last_movements" and item.lawsuit_external_id in matched_ids:
                    movement_count += 1
            offset += len(records)
    return EnrichmentCoverage(
        referenced_customers=len(customer_ids),
        customers_found=len(found_customers),
        transactions_found=len(transaction_ids),
        last_movements_found=movement_count,
    )

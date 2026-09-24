"""Resumable, page-atomic Advbox reconciliation with no response-body logging."""

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from partner_reports.contracts.ingestion import (
    AdvboxCustomerInput,
    AdvboxLawsuitInput,
    AdvboxMovementInput,
    AdvboxTransactionInput,
)
from partner_reports.integrations.advbox.client import (
    AdvboxAuditError,
    AdvboxClient,
    AdvboxRateLimitError,
    AdvboxServerError,
    AdvboxTransportError,
    AdvboxUnexpectedResponse,
)
from partner_reports.integrations.advbox.normalize import normalize_record, report_hash
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

RESOURCES = ("customers", "lawsuits", "transactions", "last_movements")
PAGE_SIZE = 100


@dataclass(frozen=True)
class SyncSummary:
    resource: str
    status: str
    pages: int
    fetched: int
    inserted: int
    updated: int
    errors: int
    changed_partners: int
    next_offset: int
    expected_total: int | None


def _page(payload: Any, *, requested_offset: int, requested_limit: int) -> tuple[list[Any], int]:
    if not isinstance(payload, Mapping):
        raise AdvboxUnexpectedResponse("coleção não retornou objeto JSON")
    records, total = payload.get("data"), payload.get("totalCount")
    if not isinstance(records, list) or not isinstance(total, int) or isinstance(total, bool):
        raise AdvboxUnexpectedResponse("coleção sem data/totalCount válidos")
    if total < 0 or len(records) > requested_limit:
        raise AdvboxUnexpectedResponse("total ou tamanho da página inválido")
    if not all(isinstance(record, Mapping) for record in records):
        raise AdvboxUnexpectedResponse("item da coleção inválido")
    if payload.get("offset") != requested_offset or payload.get("limit") != requested_limit:
        raise AdvboxUnexpectedResponse("offset/limit da resposta divergentes")
    if requested_offset < total and not records:
        raise AdvboxUnexpectedResponse("página vazia antes de totalCount")
    if requested_offset + len(records) > total:
        raise AdvboxUnexpectedResponse("página excedeu totalCount")
    return records, total


def _eligible_link_filter(today: date) -> Any:
    return (
        (PartnerCaseLink.status == "active")
        & (PartnerCaseLink.valid_from <= today)
        & or_(PartnerCaseLink.valid_to.is_(None), PartnerCaseLink.valid_to >= today)
    )


def _mark_partners(session: Session, run_id: uuid.UUID, partner_ids: set[uuid.UUID]) -> None:
    for partner_id in partner_ids:
        session.execute(
            insert(SyncChangedPartner)
            .values(id=uuid.uuid4(), sync_run_id=run_id, partner_id=partner_id)
            .on_conflict_do_nothing(constraint="uq_sync_changed_partners_run_partner")
        )


def _partners_for_customer(session: Session, customer_id: uuid.UUID) -> set[uuid.UUID]:
    eligible = _eligible_link_filter(date.today())
    direct = session.scalars(
        select(PartnerCaseLink.partner_id).where(
            eligible, PartnerCaseLink.customer_id == customer_id
        )
    ).all()
    via_lawsuit = session.scalars(
        select(PartnerCaseLink.partner_id)
        .join(LawsuitCustomer, LawsuitCustomer.lawsuit_id == PartnerCaseLink.lawsuit_id)
        .where(eligible, LawsuitCustomer.customer_id == customer_id)
    ).all()
    return set(direct) | set(via_lawsuit)


def _partners_for_lawsuit(session: Session, lawsuit_id: uuid.UUID) -> set[uuid.UUID]:
    eligible = _eligible_link_filter(date.today())
    direct = session.scalars(
        select(PartnerCaseLink.partner_id).where(eligible, PartnerCaseLink.lawsuit_id == lawsuit_id)
    ).all()
    via_customer = session.scalars(
        select(PartnerCaseLink.partner_id)
        .join(LawsuitCustomer, LawsuitCustomer.customer_id == PartnerCaseLink.customer_id)
        .where(eligible, LawsuitCustomer.lawsuit_id == lawsuit_id)
    ).all()
    return set(direct) | set(via_customer)


def _missing_reference(session: Session, run: SyncRun, offset: int, code: str) -> None:
    session.add(
        SyncError(
            sync_run_id=run.id,
            resource_type=run.resource_type,
            error_code=code,
            retryable=True,
            page_offset=offset,
        )
    )


def _upsert_customer(
    session: Session, run: SyncRun, item: AdvboxCustomerInput
) -> tuple[bool, bool]:
    digest = report_hash(item)
    row = session.scalar(select(Customer).where(Customer.advbox_id == item.external_id))
    if row is None:
        row = Customer(advbox_id=item.external_id)
        session.add(row)
        inserted, updated = True, False
    else:
        inserted, updated = False, row.report_hash != digest or row.status != "active"
    if inserted or updated:
        row.name = item.name
        row.identification = item.identification
        row.origin = item.origin
        row.source_created_at = item.source_created_at
        row.report_hash = digest
        row.synced_at = datetime.now(UTC)
        row.status = "active"
        row.deleted_at = None
        session.flush()
        _mark_partners(session, run.id, _partners_for_customer(session, row.id))
    return inserted, updated


def _upsert_lawsuit(
    session: Session, run: SyncRun, item: AdvboxLawsuitInput, offset: int
) -> tuple[bool, bool]:
    digest = report_hash(item)
    row = session.scalar(select(Lawsuit).where(Lawsuit.advbox_id == item.external_id))
    if row is None:
        row = Lawsuit(advbox_id=item.external_id)
        session.add(row)
        inserted, updated = True, False
    else:
        inserted, updated = False, row.report_hash != digest or row.status != "active"
    if inserted or updated:
        row.process_number = item.process_number
        row.protocol_number = item.protocol_number
        row.folder = item.folder
        row.group_id = item.group_id
        row.lawsuit_type_id = item.lawsuit_type_id
        row.stage_id = item.stage_id
        row.responsible_id = item.responsible_id
        row.process_date = item.process_date
        row.source_created_at = item.source_created_at
        row.report_hash = digest
        row.synced_at = datetime.now(UTC)
        row.status = "active"
        row.deleted_at = None
        session.flush()

    existing_links = {
        link.customer_id: link
        for link in session.scalars(
            select(LawsuitCustomer).where(LawsuitCustomer.lawsuit_id == row.id)
        )
    }
    referenced_customers = {
        customer.advbox_id: customer.id
        for customer in session.scalars(
            select(Customer).where(Customer.advbox_id.in_(item.customer_external_ids))
        )
    }
    desired_ids = set(referenced_customers.values())
    for customer_id in item.customer_external_ids:
        if customer_id not in referenced_customers:
            _missing_reference(session, run, offset, "missing_customer")
    for customer_id, link in existing_links.items():
        if customer_id not in desired_ids:
            session.delete(link)
    for customer_id in desired_ids - existing_links.keys():
        session.add(LawsuitCustomer(lawsuit_id=row.id, customer_id=customer_id))
    if inserted or updated or desired_ids != existing_links.keys():
        session.flush()
        _mark_partners(session, run.id, _partners_for_lawsuit(session, row.id))
    return inserted, updated


def _upsert_transaction(
    session: Session, run: SyncRun, item: AdvboxTransactionInput, offset: int
) -> tuple[bool, bool]:
    digest = report_hash(item)
    lawsuit = (
        session.scalar(select(Lawsuit).where(Lawsuit.advbox_id == item.lawsuit_external_id))
        if item.lawsuit_external_id is not None
        else None
    )
    if item.lawsuit_external_id is not None and lawsuit is None:
        _missing_reference(session, run, offset, "missing_lawsuit")
    row = session.scalar(
        select(FinancialTransaction).where(FinancialTransaction.advbox_id == item.external_id)
    )
    if row is None:
        row = FinancialTransaction(advbox_id=item.external_id)
        session.add(row)
        inserted, updated = True, False
    else:
        inserted = False
        updated = row.report_hash != digest or row.lawsuit_id != (lawsuit.id if lawsuit else None)
    if inserted or updated:
        previous_lawsuit_id = row.lawsuit_id
        row.lawsuit_id = lawsuit.id if lawsuit else None
        row.amount = item.amount
        row.amount_status = item.amount_status.value
        row.entry_type = item.entry_type
        row.category = item.category
        row.cost_center = item.cost_center
        row.competence = item.competence
        row.date_due = item.date_due
        row.date_payment = item.date_payment
        row.is_internal = item.is_internal
        row.report_hash = digest
        row.synced_at = datetime.now(UTC)
        session.flush()
        for lawsuit_id in {previous_lawsuit_id, row.lawsuit_id} - {None}:
            _mark_partners(session, run.id, _partners_for_lawsuit(session, lawsuit_id))
    return inserted, updated


def _upsert_movement(
    session: Session, run: SyncRun, item: AdvboxMovementInput, offset: int
) -> tuple[bool, bool]:
    lawsuit = session.scalar(select(Lawsuit).where(Lawsuit.advbox_id == item.lawsuit_external_id))
    if lawsuit is None:
        _missing_reference(session, run, offset, "missing_lawsuit")
        return False, False
    existing = session.scalar(
        select(Movement).where(
            Movement.lawsuit_id == lawsuit.id,
            Movement.source_fingerprint == item.source_fingerprint,
        )
    )
    if existing is not None:
        return False, False
    session.add(
        Movement(
            lawsuit_id=lawsuit.id,
            source_fingerprint=item.source_fingerprint,
            occurred_at=item.occurred_at,
            title=item.title,
        )
    )
    session.flush()
    _mark_partners(session, run.id, _partners_for_lawsuit(session, lawsuit.id))
    return True, False


_UPSERT = {
    "customers": _upsert_customer,
    "lawsuits": _upsert_lawsuit,
    "transactions": _upsert_transaction,
    "last_movements": _upsert_movement,
}


def _error_code(error: Exception) -> tuple[str, int | None, bool]:
    if isinstance(error, AdvboxRateLimitError):
        return "rate_limit", 429, True
    if isinstance(error, AdvboxServerError):
        return "server_error", None, True
    if isinstance(error, AdvboxTransportError):
        return "transport_error", None, True
    if isinstance(error, (AdvboxUnexpectedResponse, ValidationError)):
        return "invalid_response", None, False
    if isinstance(error, AdvboxAuditError):
        return type(error).__name__.lower(), None, False
    return "processing_error", None, False


class SyncRunner:
    """One shared client scans each resource once; every DB page is atomic."""

    def __init__(self, client: AdvboxClient, session_factory: Callable[[], Session]) -> None:
        self.client = client
        self.session_factory = session_factory

    async def run_resource(
        self,
        resource: str,
        *,
        batch_key: str,
        dry_run: bool = False,
        reprocess: bool = False,
        max_pages: int | None = None,
    ) -> SyncSummary:
        if resource not in RESOURCES or not batch_key or len(batch_key) > 95:
            raise ValueError("recurso ou chave de lote inválidos")
        if max_pages is not None and max_pages < 1:
            raise ValueError("max_pages deve ser positivo")
        run_key = f"{batch_key}:{resource}"
        offset, expected_total, pages = 0, None, 0
        fetched = 0
        if not dry_run:
            with self.session_factory() as session, session.begin():
                run = session.scalar(select(SyncRun).where(SyncRun.idempotency_key == run_key))
                if run is None:
                    if reprocess:
                        raise ValueError("lote de reprocessamento inexistente")
                    run = SyncRun(
                        idempotency_key=run_key,
                        resource_type=resource,
                        status="running",
                        started_at=datetime.now(UTC),
                        next_offset=0,
                        fetched_count=0,
                        inserted_count=0,
                        updated_count=0,
                        error_count=0,
                    )
                    session.add(run)
                    session.flush()
                if run.resource_type != resource:
                    raise ValueError("recurso do lote incompatível")
                if reprocess:
                    pending_offset = session.scalar(
                        select(func.min(SyncError.page_offset)).where(
                            SyncError.sync_run_id == run.id, SyncError.resolved_at.is_(None)
                        )
                    )
                    if pending_offset is None:
                        return self._summary(session, run, 0)
                    offset = pending_offset
                elif run.status == "succeeded":
                    return self._summary(session, run, 0)
                else:
                    offset = run.next_offset or 0
                expected_total = run.expected_total
                run.status = "running"
                run.finished_at = None

        while expected_total is None or offset < expected_total:
            if max_pages is not None and pages >= max_pages:
                break
            try:
                response = await self.client.list_page(resource, limit=PAGE_SIZE, offset=offset)
                records, total = _page(
                    response.payload, requested_offset=offset, requested_limit=PAGE_SIZE
                )
                if expected_total is not None and expected_total != total:
                    raise AdvboxUnexpectedResponse("totalCount mudou; reiniciar lote")
                items = [normalize_record(resource, record) for record in records]
                ids = [
                    item.source_fingerprint if resource == "last_movements" else item.external_id
                    for item in items
                ]
                if len(ids) != len(set(ids)):
                    raise AdvboxUnexpectedResponse("IDs duplicados na página")
                if dry_run:
                    fetched += len(items)
                else:
                    with self.session_factory() as session, session.begin():
                        run = session.scalar(
                            select(SyncRun)
                            .where(SyncRun.idempotency_key == run_key)
                            .with_for_update()
                        )
                        assert run is not None
                        if run.expected_total is not None and run.expected_total != total:
                            raise AdvboxUnexpectedResponse("totalCount mudou; reiniciar lote")
                        for error in session.scalars(
                            select(SyncError).where(
                                SyncError.sync_run_id == run.id,
                                SyncError.page_offset == offset,
                                SyncError.resolved_at.is_(None),
                            )
                        ):
                            error.resolved_at = datetime.now(UTC)
                        page_inserted = page_updated = 0
                        for item in items:
                            operation = _UPSERT[resource]
                            if resource == "customers":
                                was_inserted, was_updated = operation(session, run, item)
                            else:
                                was_inserted, was_updated = operation(session, run, item, offset)
                            page_inserted += was_inserted
                            page_updated += was_updated
                        run.expected_total = total
                        run.next_offset = offset + len(items)
                        run.fetched_count += len(items)
                        run.inserted_count += page_inserted
                        run.updated_count += page_updated
                        run.error_count = (
                            session.scalar(
                                select(func.count())
                                .select_from(SyncError)
                                .where(
                                    SyncError.sync_run_id == run.id,
                                    SyncError.resolved_at.is_(None),
                                )
                            )
                            or 0
                        )
                pages += 1
                expected_total = total
                offset += len(items)
            except Exception as error:
                if not dry_run:
                    code, status, retryable = _error_code(error)
                    with self.session_factory() as session, session.begin():
                        run = session.scalar(
                            select(SyncRun)
                            .where(SyncRun.idempotency_key == run_key)
                            .with_for_update()
                        )
                        assert run is not None
                        existing = session.scalar(
                            select(SyncError).where(
                                SyncError.sync_run_id == run.id,
                                SyncError.page_offset == offset,
                                SyncError.error_code == code,
                                SyncError.resolved_at.is_(None),
                            )
                        )
                        if existing is None:
                            session.add(
                                SyncError(
                                    sync_run_id=run.id,
                                    resource_type=resource,
                                    error_code=code,
                                    http_status=status,
                                    retryable=retryable,
                                    page_offset=offset,
                                )
                            )
                        run.status = "partial" if run.fetched_count else "failed"
                        run.finished_at = datetime.now(UTC)
                        run.error_count = (run.error_count or 0) + (existing is None)
                raise SyncFailure(resource, offset, _error_code(error)[0]) from None

        if dry_run:
            return SyncSummary(
                resource, "dry_run", pages, fetched, 0, 0, 0, 0, offset, expected_total
            )
        with self.session_factory() as session, session.begin():
            run = session.scalar(
                select(SyncRun).where(SyncRun.idempotency_key == run_key).with_for_update()
            )
            assert run is not None
            run.error_count = (
                session.scalar(
                    select(func.count())
                    .select_from(SyncError)
                    .where(SyncError.sync_run_id == run.id, SyncError.resolved_at.is_(None))
                )
                or 0
            )
            run.status = (
                "succeeded"
                if expected_total is not None and offset >= expected_total and not run.error_count
                else "partial"
            )
            run.finished_at = datetime.now(UTC)
            return self._summary(session, run, pages)

    @staticmethod
    def _summary(session: Session, run: SyncRun, pages: int) -> SyncSummary:
        changed = (
            session.scalar(
                select(func.count())
                .select_from(SyncChangedPartner)
                .where(SyncChangedPartner.sync_run_id == run.id)
            )
            or 0
        )
        return SyncSummary(
            run.resource_type,
            run.status,
            pages,
            run.fetched_count,
            run.inserted_count,
            run.updated_count,
            run.error_count,
            changed,
            run.next_offset or 0,
            run.expected_total,
        )


class SyncFailure(RuntimeError):
    """Sanitized failure without upstream response or record values."""

    def __init__(self, resource: str, offset: int, code: str) -> None:
        super().__init__(f"{resource} offset={offset}: {code}")

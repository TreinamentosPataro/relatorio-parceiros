"""Allowlisted normalization; raw Advbox dictionaries never reach persistence."""

import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from partner_reports.contracts.common import AvailabilityStatus
from partner_reports.contracts.ingestion import (
    AdvboxCustomerInput,
    AdvboxLawsuitInput,
    AdvboxMovementInput,
    AdvboxTransactionInput,
)
from partner_reports.integrations.advbox.client import AdvboxUnexpectedResponse

_SOURCE_ZONE = ZoneInfo("America/Sao_Paulo")


def _positive_id(value: Any, *, required: bool = False) -> int | None:
    if value is None or value == "" or value == 0:
        if required:
            raise AdvboxUnexpectedResponse("registro sem ID técnico válido")
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AdvboxUnexpectedResponse("ID técnico inválido")
    return value


def _text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise AdvboxUnexpectedResponse("campo textual inválido")
    return value


def _date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise AdvboxUnexpectedResponse("data inválida")
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise AdvboxUnexpectedResponse("data inválida") from None


def _datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise AdvboxUnexpectedResponse("data/hora inválida")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise AdvboxUnexpectedResponse("data/hora inválida") from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_SOURCE_ZONE)


def normalize_record(resource: str, raw: Mapping[str, Any]) -> Any:
    """Reject malformed fields and ignore all unapproved source attributes."""

    if resource == "last_movements":
        lawsuit_id = _positive_id(raw.get("lawsuit_id"), required=True)
        occurred_at = _datetime(raw.get("date"))
        title = _text(raw.get("title"))
        if occurred_at is None:
            raise AdvboxUnexpectedResponse("andamento sem data")
        fingerprint_input = json.dumps(
            [lawsuit_id, occurred_at.isoformat(), title],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return AdvboxMovementInput(
            lawsuit_external_id=lawsuit_id,
            source_fingerprint=hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest(),
            occurred_at=occurred_at,
            title=title,
        )
    external_id = _positive_id(raw.get("id"), required=True)
    if resource == "customers":
        return AdvboxCustomerInput(
            external_id=external_id,
            name=_text(raw.get("name")),
            identification=_text(raw.get("identification")),
            origin=_text(raw.get("origin")),
            source_created_at=_datetime(raw.get("created_at")),
        )
    if resource == "lawsuits":
        related = raw.get("customers", [])
        if not isinstance(related, list) or not all(isinstance(x, Mapping) for x in related):
            raise AdvboxUnexpectedResponse("relação processo-cliente inválida")
        customer_ids = tuple(
            sorted(
                {
                    identifier
                    for customer in related
                    if (identifier := _positive_id(customer.get("customer_id"))) is not None
                }
            )
        )
        return AdvboxLawsuitInput(
            external_id=external_id,
            process_number=_text(raw.get("process_number")),
            protocol_number=_text(raw.get("protocol_number")),
            folder=_text(raw.get("folder")),
            group_id=_positive_id(raw.get("group_id")),
            lawsuit_type_id=_positive_id(raw.get("type_lawsuit_id")),
            stage_id=_positive_id(raw.get("stages_id")),
            responsible_id=_positive_id(raw.get("responsible_id")),
            process_date=_date(raw.get("process_date")),
            source_created_at=_datetime(raw.get("created_at")),
            customer_external_ids=customer_ids,
        )
    if resource == "transactions":
        amount = raw.get("amount")
        if amount is not None and (
            isinstance(amount, bool) or not isinstance(amount, (int, Decimal))
        ):
            raise AdvboxUnexpectedResponse("valor financeiro inválido")
        internal = raw.get("is_internal")
        if internal is not None and not isinstance(internal, bool):
            raise AdvboxUnexpectedResponse("indicador interno inválido")
        return AdvboxTransactionInput(
            external_id=external_id,
            lawsuit_external_id=_positive_id(raw.get("lawsuit_id")),
            amount=Decimal(str(amount)) if amount is not None else None,
            amount_status=(
                AvailabilityStatus.AVAILABLE
                if amount is not None
                else AvailabilityStatus.NOT_PROVIDED
            ),
            entry_type=_text(raw.get("entry_type")),
            category=_text(raw.get("category")),
            cost_center=_text(raw.get("cost_center")),
            competence=_text(raw.get("competence")),
            date_due=_date(raw.get("date_due")),
            date_payment=_date(raw.get("date_payment")),
            is_internal=internal,
        )
    raise ValueError("recurso desconhecido")


def report_hash(item: Any) -> str:
    """Stable SHA-256 over only the normalized, report-relevant fields."""

    encoded = json.dumps(item.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

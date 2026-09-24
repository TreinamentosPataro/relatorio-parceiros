"""Sanitize small Advbox samples and inspect only their structural contract."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from partner_reports.integrations.advbox.client import (
    AdvboxAuditClient,
    AdvboxAuditError,
    AdvboxAuthenticationError,
    AdvboxForbiddenError,
)

_PARTNER_TERMS = (
    "partner",
    "parceiro",
    "origin",
    "origem",
    "indication",
    "indicacao",
    "referrer",
    "responsible",
    "responsavel",
    "tag",
    "folder",
    "pasta",
    "portfolio",
    "carteira",
)


class LinkageStatus(StrEnum):
    """Allowed conclusions for the partner-to-portfolio gate."""

    CONFIRMADO = "CONFIRMADO"
    AUSENTE = "AUSENTE"
    INCONCLUSIVO = "INCONCLUSIVO"


@dataclass(frozen=True)
class FieldObservation:
    path: str
    types: tuple[str, ...]
    observed_count: int
    null_count: int


@dataclass(frozen=True)
class PaginationObservation:
    style: str
    total_count: int | None
    limit: int | None
    offset: int | None


@dataclass(frozen=True)
class ResourceObservation:
    resource: str
    endpoint_template: str
    status_code: int | None
    duration_ms: int | None
    item_count: int | None
    fields: tuple[FieldObservation, ...] = ()
    pagination: PaginationObservation | None = None
    id_fields: tuple[str, ...] = ()
    date_fields: tuple[str, ...] = ()
    relationship_fields: tuple[str, ...] = ()
    null_fields: tuple[str, ...] = ()
    partner_candidate_fields: tuple[str, ...] = ()
    safe_error: str | None = None


@dataclass(frozen=True)
class AuditRunResult:
    started_at: datetime
    finished_at: datetime
    observations: tuple[ResourceObservation, ...]
    linkage_status: LinkageStatus
    linkage_evidence: tuple[str, ...]


@dataclass
class _MutableFieldStats:
    types: set[str]
    observed_count: int = 0
    null_count: int = 0


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, (float, Decimal)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "array"
    return type(value).__name__


def _walk_schema(
    value: Any,
    path: str,
    stats: defaultdict[str, _MutableFieldStats],
) -> None:
    if path:
        entry = stats[path]
        entry.types.add(_type_name(value))
        entry.observed_count += 1
        if value is None:
            entry.null_count += 1

    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            nested_path = f"{path}.{key}" if path else str(key)
            _walk_schema(nested_value, nested_path, stats)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested_value in value[:20]:
            _walk_schema(nested_value, f"{path}[]", stats)


def _integer_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _detect_pagination(payload: Any) -> PaginationObservation | None:
    if not isinstance(payload, Mapping):
        return None
    keys = set(payload)
    if {"data", "limit", "offset"}.issubset(keys):
        return PaginationObservation(
            style="offset/limit",
            total_count=_integer_or_none(payload.get("totalCount")),
            limit=_integer_or_none(payload.get("limit")),
            offset=_integer_or_none(payload.get("offset")),
        )
    if "next" in keys or "nextCursor" in keys:
        return PaginationObservation("cursor", None, None, None)
    return None


def _record_count(payload: Any) -> int:
    if payload is None:
        return 0
    if isinstance(payload, Mapping) and isinstance(payload.get("data"), list):
        return len(payload["data"])
    if isinstance(payload, list):
        return len(payload)
    return 1 if isinstance(payload, Mapping) else 0


def sanitize_payload(
    *,
    resource: str,
    endpoint_template: str,
    status_code: int,
    duration_ms: int,
    payload: Any,
) -> ResourceObservation:
    """Discard values and retain only field paths, types, nulls, counts, and pagination."""

    stats: defaultdict[str, _MutableFieldStats] = defaultdict(
        lambda: _MutableFieldStats(types=set())
    )
    _walk_schema(payload, "", stats)
    fields = tuple(
        FieldObservation(
            path=path,
            types=tuple(sorted(field_stats.types)),
            observed_count=field_stats.observed_count,
            null_count=field_stats.null_count,
        )
        for path, field_stats in sorted(stats.items())
    )
    paths = tuple(field.path for field in fields)

    def leaf(path: str) -> str:
        return path.removesuffix("[]").rsplit(".", 1)[-1].lower()

    id_fields = tuple(
        path for path in paths if leaf(path) == "id" or leaf(path).endswith(("_id", "_ids"))
    )
    date_fields = tuple(
        path
        for path in paths
        if any(term in leaf(path) for term in ("date", "created", "updated", "timestamp"))
    )
    relationship_fields = tuple(
        path
        for path in paths
        if path in id_fields or leaf(path).endswith(("customer", "lawsuit", "user", "owner"))
    )
    null_fields = tuple(field.path for field in fields if field.null_count)
    partner_fields = tuple(
        path for path in paths if any(term in path.lower() for term in _PARTNER_TERMS)
    )

    return ResourceObservation(
        resource=resource,
        endpoint_template=endpoint_template,
        status_code=status_code,
        duration_ms=duration_ms,
        item_count=_record_count(payload),
        fields=fields,
        pagination=_detect_pagination(payload),
        id_fields=id_fields,
        date_fields=date_fields,
        relationship_fields=relationship_fields,
        null_fields=null_fields,
        partner_candidate_fields=partner_fields,
    )


def _first_lawsuit_id(payload: Any) -> str | int | None:
    if not isinstance(payload, Mapping):
        return None
    data = payload.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], Mapping):
        return None
    identifier = data[0].get("id")
    if isinstance(identifier, (str, int)) and not isinstance(identifier, bool):
        return identifier
    return None


def classify_linkage(
    observations: Sequence[ResourceObservation],
) -> tuple[LinkageStatus, tuple[str, ...]]:
    """Confirm only a direct partner field; never infer absence from a small sample."""

    direct_fields: list[str] = []
    for observation in observations:
        if observation.resource not in {"customers", "lawsuits"}:
            continue
        for path in observation.partner_candidate_fields:
            lowered = path.lower()
            if "partner" not in lowered and "parceiro" not in lowered:
                continue
            field = next(item for item in observation.fields if item.path == path)
            has_observed_value = field.null_count < field.observed_count
            is_direct_relation = lowered.endswith(("partner_id", "partnerid", "parceiro_id"))
            is_nested_id = lowered.endswith(("partner.id", "parceiro.id"))
            if has_observed_value and (is_direct_relation or is_nested_id):
                direct_fields.append(f"{observation.resource}: {path}")
    if direct_fields:
        return LinkageStatus.CONFIRMADO, tuple(sorted(set(direct_fields)))

    successful_core = {
        observation.resource
        for observation in observations
        if observation.resource in {"customers", "lawsuits", "settings"}
        and observation.status_code is not None
        and 200 <= observation.status_code < 300
    }
    if successful_core == {"customers", "lawsuits", "settings"}:
        return (
            LinkageStatus.INCONCLUSIVO,
            (
                "A amostra estrutural não expôs campo direto partner/parceiro.",
                "Amostragem mínima não prova ausência em toda a carteira nem unicidade do vínculo.",
            ),
        )
    return (
        LinkageStatus.INCONCLUSIVO,
        ("Não foi possível auditar com sucesso todos os recursos centrais.",),
    )


class AdvboxAuditRunner:
    """Run the documented minimum sample without retaining production bodies."""

    _STATIC_REQUESTS = (
        ("settings", "/settings", None),
        ("customers", "/customers", {"limit": 1, "offset": 0}),
        ("lawsuits", "/lawsuits", {"limit": 1, "offset": 0}),
        ("last_movements", "/last_movements", {"limit": 1, "offset": 0}),
        ("transactions", "/transactions", {"limit": 1, "offset": 0}),
    )

    def __init__(self, client: AdvboxAuditClient) -> None:
        self._client = client

    async def run(self) -> AuditRunResult:
        """Collect sanitized observations and conditionally inspect one lawsuit relation."""

        started_at = datetime.now(UTC)
        observations: list[ResourceObservation] = []
        lawsuit_id: str | int | None = None

        for resource, endpoint, params in self._STATIC_REQUESTS:
            try:
                result = await self._client.get(endpoint, params=params)
                if resource == "lawsuits":
                    lawsuit_id = _first_lawsuit_id(result.payload)
                observations.append(
                    sanitize_payload(
                        resource=resource,
                        endpoint_template=endpoint,
                        status_code=result.status_code,
                        duration_ms=result.duration_ms,
                        payload=result.payload,
                    )
                )
            except AdvboxAuditError as exc:
                observations.append(
                    ResourceObservation(
                        resource=resource,
                        endpoint_template=endpoint,
                        status_code=None,
                        duration_ms=None,
                        item_count=None,
                        safe_error=str(exc),
                    )
                )
                if isinstance(exc, (AdvboxAuthenticationError, AdvboxForbiddenError)):
                    break

        if lawsuit_id is not None:
            for resource, endpoint_template in (
                ("movements", "/movements/{lawsuit_id}"),
                ("history", "/history/{lawsuit_id}"),
            ):
                endpoint = endpoint_template.format(lawsuit_id=lawsuit_id)
                try:
                    result = await self._client.get(endpoint)
                    observations.append(
                        sanitize_payload(
                            resource=resource,
                            endpoint_template=endpoint_template,
                            status_code=result.status_code,
                            duration_ms=result.duration_ms,
                            payload=result.payload,
                        )
                    )
                except AdvboxAuditError as exc:
                    observations.append(
                        ResourceObservation(
                            resource=resource,
                            endpoint_template=endpoint_template,
                            status_code=None,
                            duration_ms=None,
                            item_count=None,
                            safe_error=str(exc),
                        )
                    )

        linkage_status, evidence = classify_linkage(observations)
        return AuditRunResult(
            started_at=started_at,
            finished_at=datetime.now(UTC),
            observations=tuple(observations),
            linkage_status=linkage_status,
            linkage_evidence=evidence,
        )

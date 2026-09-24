"""Allowlisted security audit events: no request path, payload, secret or free text."""

import json
import logging
import uuid

from fastapi import Request
from sqlalchemy.orm import Session

from partner_reports.persistence.models import AuditEvent

_ACTIONS = frozenset(
    {
        "login_succeeded",
        "login_failed",
        "login_limited",
        "logout",
        "catalog_view",
        "partner_view",
        "report_view",
        "report_download",
        "artifact_denied",
        "generation_requested",
        "account_created",
        "account_disabled",
        "sessions_revoked",
        "security_metadata_purged",
        "link_changed",
        "pdf_upload_succeeded",
        "pdf_upload_rejected",
        "pdf_upload_duplicate",
        "pdf_upload_failed",
    }
)
_ENTITIES = frozenset({"none", "user", "partner", "report_version", "pdf_import_batch"})
_REASONS = frozenset(
    {
        "invalid_credentials",
        "rate_limited",
        "access_denied",
        "FILE_EMPTY",
        "FILE_NOT_PDF",
        "PDF_MALFORMED",
        "PDF_ENCRYPTED",
        "SIZE_LIMIT_EXCEEDED",
        "PAGE_LIMIT_EXCEEDED",
        "PAGE_FORMAT_UNSUPPORTED",
        "PDF_ANNOTATED_SOURCE",
        "SOURCE_SCOPE_INVALID",
        "DUPLICATE_SOURCE",
        "STORAGE_UNAVAILABLE",
    }
)
_LOGGER = logging.getLogger("partner_reports.security")
_LOGGER.setLevel(logging.INFO)


def record_audit(
    db: Session,
    *,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    entity_type: str = "none",
    entity_id: uuid.UUID | None = None,
    reason_code: str | None = None,
    correlation_id: uuid.UUID | None = None,
) -> AuditEvent:
    """Persist an enum-like event; reject untrusted/free-form fields by default."""

    if action not in _ACTIONS or entity_type not in _ENTITIES:
        raise ValueError("evento de auditoria não classificado")
    if reason_code is not None and reason_code not in _REASONS:
        raise ValueError("motivo de auditoria não classificado")
    event = AuditEvent(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        correlation_id=correlation_id or uuid.uuid4(),
        changed_fields=[],
        reason_code=reason_code,
    )
    db.add(event)
    db.flush()
    return event


def request_correlation_id(request: Request) -> uuid.UUID:
    """Only a server-created opaque ID is used; never trust a client-supplied ID."""

    if not hasattr(request.state, "correlation_id"):
        request.state.correlation_id = uuid.uuid4()
    return request.state.correlation_id


def emit_audit(event: AuditEvent) -> None:
    """Log only allowlisted technical metadata after a successful DB commit."""

    _LOGGER.info(
        json.dumps(
            {
                "event": event.action,
                "correlation_id": str(event.correlation_id),
                "entity_type": event.entity_type,
            },
            separators=(",", ":"),
        )
    )

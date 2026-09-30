"""Single source of truth for which partners the configured data scope admits."""

from typing import Protocol

from sqlalchemy import ColumnElement, and_

from partner_reports.config import PdfDataScope, Settings
from partner_reports.persistence.models import Partner

SYNTHETIC_PREFIX = "SYNTHETIC-"


class _ScopedPartner(Protocol):
    external_id: str
    pilot_enabled: bool


def partner_scope_clause(settings: Settings | None) -> ColumnElement[bool]:
    """SQL filter: synthetic partners, or real partners explicitly enabled for the pilot."""

    if settings is None or settings.pdf_data_scope is PdfDataScope.SYNTHETIC_ONLY:
        return Partner.external_id.startswith(SYNTHETIC_PREFIX)
    return and_(
        Partner.pilot_enabled.is_(True),
        ~Partner.external_id.startswith(SYNTHETIC_PREFIX),
    )


def partner_in_scope(settings: Settings | None, partner: _ScopedPartner | None) -> bool:
    """Python counterpart of :func:`partner_scope_clause`; absent partner is out of scope."""

    if partner is None:
        return False
    synthetic = partner.external_id.startswith(SYNTHETIC_PREFIX)
    if settings is None or settings.pdf_data_scope is PdfDataScope.SYNTHETIC_ONLY:
        return synthetic
    return partner.pilot_enabled is True and not synthetic

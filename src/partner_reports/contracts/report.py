"""Allowlisted report projection; free-form source fields are deliberately absent."""

import uuid
from datetime import date, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict

from partner_reports.contracts.common import AvailabilityStatus, MoneyValue


class ReportCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: uuid.UUID
    status_key: str
    process_date: date | None = None
    financial_total: MoneyValue


class ReportSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    section_key: str
    availability_status: AvailabilityStatus
    reason_code: str | None = None


class PartnerReport(BaseModel):
    """External-facing contract with a deliberate, minimal allowlist."""

    model_config = ConfigDict(frozen=True)

    report_version_id: uuid.UUID
    partner_id: uuid.UUID
    period_start: date
    period_end: date
    generated_at: AwareDatetime
    cases: tuple[ReportCase, ...]
    sections: tuple[ReportSection, ...]

    @property
    def generated_datetime(self) -> datetime:
        return self.generated_at

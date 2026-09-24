"""Typed, privacy-minimized internal and partner report projections."""

import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, model_validator

from partner_reports.contracts.common import AvailabilityStatus, StrictDecimal

NonNegativeInt = Annotated[StrictInt, Field(ge=0)]


class ReportValue[T](BaseModel):
    """One value with explicit availability, provenance and validation time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: AvailabilityStatus
    value: T | None = None
    source: str = Field(min_length=1, max_length=100)
    as_of: AwareDatetime
    last_validated_at: AwareDatetime | None = None
    reason_code: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_availability(self) -> "ReportValue[T]":
        if self.status is AvailabilityStatus.AVAILABLE and self.value is None:
            raise ValueError("available exige valor, inclusive zero explícito")
        if self.status is not AvailabilityStatus.AVAILABLE and self.value is not None:
            raise ValueError("valor indisponível deve ser nulo")
        return self


class SafePartnerIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


class PortfolioTotals(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    unique_customers: NonNegativeInt
    lawsuits: NonNegativeInt


class MetricSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    unique_customers: ReportValue[NonNegativeInt]
    lawsuits: ReportValue[NonNegativeInt]
    benefits_granted: ReportValue[NonNegativeInt]
    in_financial: ReportValue[NonNegativeInt]
    in_judicial: ReportValue[NonNegativeInt]


class DistributionSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    by_stage: ReportValue[dict[str, NonNegativeInt]]
    by_legal_status: ReportValue[dict[str, NonNegativeInt]]
    by_area: ReportValue[dict[str, NonNegativeInt]]


class CustomerView(BaseModel):
    """Partner-visible association without name, document or contact details."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: ReportValue[str]
    lawsuit_references: ReportValue[tuple[str, ...]]


class CaseView(BaseModel):
    """Partner-visible case data; free movement text is never a field here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: ReportValue[str]
    customer_references: ReportValue[tuple[str, ...]]
    latest_recorded_movement_at: ReportValue[AwareDatetime]
    latest_relevant_movement_at: ReportValue[AwareDatetime]
    executive_status: ReportValue[str]


class FinancialSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    partner_due: StrictDecimal
    currency: str = "BRL"


class QualityAlert(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1, max_length=100)
    count: ReportValue[NonNegativeInt]


class ReportMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    period_start: date
    period_end: date
    as_of: AwareDatetime
    generated_at: AwareDatetime
    report_version: Annotated[StrictInt, Field(gt=0)]
    rule_version: str = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_period(self) -> "ReportMetadata":
        if self.period_start > self.period_end or self.period_end != self.as_of.date():
            raise ValueError("período deve terminar na data da fotografia")
        if self.generated_at < self.as_of:
            raise ValueError("geração anterior à fotografia")
        return self


class ReportViewModel(BaseModel):
    """Strict external allowlist shared by future HTML and PDF renderers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    partner: ReportValue[SafePartnerIdentity]
    metadata: ReportValue[ReportMetadata]
    origin: ReportValue[str]
    summary: ReportValue[PortfolioTotals]
    metrics: MetricSet
    distributions: DistributionSet
    customers: ReportValue[tuple[CustomerView, ...]]
    cases: ReportValue[tuple[CaseView, ...]]
    financial: ReportValue[FinancialSummary]
    alerts: ReportValue[tuple[QualityAlert, ...]]
    publication_ready: Literal[False] = False


class InternalQuality(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    unlinked_lawsuits: NonNegativeInt
    ambiguous_lawsuits: NonNegativeInt
    missing_customer_references: NonNegativeInt
    nonexistent_link_references: NonNegativeInt
    missing_movements: NonNegativeInt


class InternalReportViewModel(BaseModel):
    """Internal audit projection; external preview is withheld on conflicts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    partner_id: uuid.UUID
    as_of: AwareDatetime
    rule_version: str
    quality: ReportValue[InternalQuality]
    linked_case_ids: ReportValue[tuple[uuid.UUID, ...]]
    linked_customer_ids: ReportValue[tuple[uuid.UUID, ...]]
    partner_preview: ReportViewModel | None = None

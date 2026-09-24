"""Domain commands independent from SQLAlchemy and raw API responses."""

import uuid
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from partner_reports.contracts.common import StrictDecimal
from partner_reports.domain.partner_linkage import AdvboxEntityType, MappingStatus


class MappingSource(StrEnum):
    MANUAL_CSV = "manual_csv"
    ADMIN = "admin"
    ADVBOX_OFFICIAL = "advbox_official"


class RoundingMode(StrEnum):
    HALF_UP = "half_up"
    HALF_EVEN = "half_even"
    DOWN = "down"
    UP = "up"


class PartnerCaseLinkInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    partner_id: uuid.UUID
    entity_type: AdvboxEntityType
    advbox_entity_id: int = Field(gt=0)
    customer_id: uuid.UUID | None = None
    lawsuit_id: uuid.UUID | None = None
    valid_from: date
    valid_to: date | None = None
    source: MappingSource
    status: MappingStatus = MappingStatus.PENDING

    @model_validator(mode="after")
    def validate_target_and_period(self) -> "PartnerCaseLinkInput":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to anterior a valid_from")
        customer_target = self.customer_id is not None and self.lawsuit_id is None
        lawsuit_target = self.lawsuit_id is not None and self.customer_id is None
        if self.entity_type is AdvboxEntityType.CUSTOMER and not customer_target:
            raise ValueError("mapeamento customer exige somente customer_id")
        if self.entity_type is AdvboxEntityType.LAWSUIT and not lawsuit_target:
            raise ValueError("mapeamento lawsuit exige somente lawsuit_id")
        return self


class FinancialAgreementInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    partner_id: uuid.UUID
    lawsuit_id: uuid.UUID
    revenue_type: str = Field(min_length=1, max_length=80)
    percentage: StrictDecimal = Field(ge=0, le=100)
    deduction_fixed_amount: StrictDecimal = Field(default="0.00", ge=0)
    deduction_percentage: StrictDecimal = Field(default="0.0000", ge=0, le=100)
    rounding_mode: RoundingMode = RoundingMode.HALF_UP
    rounding_scale: int = Field(default=2, ge=0, le=4)
    valid_from: date
    valid_to: date | None = None
    status: MappingStatus = MappingStatus.PENDING

    @model_validator(mode="after")
    def validate_period(self) -> "FinancialAgreementInput":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to anterior a valid_from")
        return self

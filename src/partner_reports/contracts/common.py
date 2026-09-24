"""Shared enums and scalar contracts with explicit absence semantics."""

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, model_validator


class AvailabilityStatus(StrEnum):
    AVAILABLE = "available"
    NOT_PROVIDED = "not_provided"
    NOT_APPLICABLE = "not_applicable"
    PENDING_VALIDATION = "pending_validation"
    RESTRICTED = "restricted"


def reject_float(value: Any) -> Any:
    """Prevent binary floating-point from entering monetary contracts."""

    if isinstance(value, float):
        raise ValueError("valores monetários devem usar Decimal ou string decimal")
    return value


StrictDecimal = Annotated[Decimal, BeforeValidator(reject_float)]


class MoneyValue(BaseModel):
    """A monetary value whose absence is never silently converted to zero."""

    model_config = ConfigDict(frozen=True)

    status: AvailabilityStatus
    value: StrictDecimal | None = None
    currency: str = "BRL"

    @model_validator(mode="after")
    def validate_state_and_value(self) -> "MoneyValue":
        if self.status is AvailabilityStatus.AVAILABLE and self.value is None:
            raise ValueError("valor é obrigatório quando status=available")
        if self.status is not AvailabilityStatus.AVAILABLE and self.value is not None:
            raise ValueError("valor deve ser nulo quando status não é available")
        return self

"""Normalized inputs accepted from the future Advbox synchronizer."""

from datetime import date

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from partner_reports.contracts.common import AvailabilityStatus, StrictDecimal


class AdvboxCustomerInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    external_id: int = Field(gt=0)
    name: str | None = Field(default=None, max_length=250, repr=False)
    identification: str | None = Field(default=None, max_length=100, repr=False)
    origin: str | None = Field(default=None, max_length=250, repr=False)
    source_created_at: AwareDatetime | None = None


class AdvboxLawsuitInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    external_id: int = Field(gt=0)
    process_number: str | None = Field(default=None, max_length=100, repr=False)
    protocol_number: str | None = Field(default=None, max_length=100, repr=False)
    folder: str | None = Field(default=None, max_length=250, repr=False)
    group_id: int | None = Field(default=None, gt=0)
    lawsuit_type_id: int | None = Field(default=None, gt=0)
    stage_id: int | None = Field(default=None, gt=0)
    responsible_id: int | None = Field(default=None, gt=0)
    process_date: date | None = None
    source_created_at: AwareDatetime | None = None
    customer_external_ids: tuple[int, ...] = ()


class AdvboxMovementInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    lawsuit_external_id: int = Field(gt=0)
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    occurred_at: AwareDatetime
    title: str | None = Field(default=None, repr=False)


class AdvboxTransactionInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    external_id: int = Field(gt=0)
    lawsuit_external_id: int | None = Field(default=None, gt=0)
    amount: StrictDecimal | None = None
    amount_status: AvailabilityStatus
    entry_type: str | None = Field(default=None, max_length=40)
    category: str | None = Field(default=None, max_length=250, repr=False)
    cost_center: str | None = Field(default=None, max_length=250, repr=False)
    competence: str | None = Field(default=None, max_length=40)
    date_due: date | None = None
    date_payment: date | None = None
    is_internal: bool | None = None

    def model_post_init(self, __context: object) -> None:
        if self.amount_status is AvailabilityStatus.AVAILABLE and self.amount is None:
            raise ValueError("amount obrigatório quando available")
        if self.amount_status is not AvailabilityStatus.AVAILABLE and self.amount is not None:
            raise ValueError("amount deve ser nulo quando indisponível")

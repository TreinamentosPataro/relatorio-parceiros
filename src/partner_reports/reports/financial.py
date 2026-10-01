"""Partner accounting rules taken from the office's own spreadsheets (ADR-007, F2).

Only three kinds of Advbox entries are read; every other category (salaries, rent,
client transfers...) is never collected nor shown.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

FINANCE_RULE_VERSION = "partner-accounting-1"
# Fixed by the office models: tax = 7.5% of the amount paid by the client.
TAX_RATE = Decimal("0.075")
_CENT = Decimal("0.01")


class EntryKind(StrEnum):
    FEE_INCOME = "fee_income"
    BANK_FEE = "bank_fee"
    PARTNER_PAYOUT = "partner_payout"


# On the same day the client's payment is listed before its fee and the payout.
_DISPLAY_ORDER = {EntryKind.FEE_INCOME: 0, EntryKind.BANK_FEE: 1, EntryKind.PARTNER_PAYOUT: 2}


def _normalized(value: str | None) -> str:
    return " ".join((value or "").upper().split())


def classify_entry(entry_type: str | None, category: str | None) -> EntryKind | None:
    """Return the accounting role of an entry, or None when it must not be read."""

    kind = _normalized(entry_type)
    name = _normalized(category)
    if kind == "INCOME" and ("HONOR" in name or name == "RPVS"):
        return EntryKind.FEE_INCOME
    if kind == "EXPENSE" and name == "TAXAS BANCÁRIAS":
        return EntryKind.BANK_FEE
    if kind == "EXPENSE" and name == "HONORÁRIOS DE PARCEIROS":
        return EntryKind.PARTNER_PAYOUT
    return None


@dataclass(frozen=True)
class FinanceEntry:
    kind: EntryKind
    category: str | None
    description: str | None
    date_due: date | None
    date_payment: date | None
    amount: Decimal | None

    @property
    def paid(self) -> bool:
        return self.date_payment is not None and self.amount is not None


@dataclass(frozen=True)
class CaseAccount:
    """Per-lawsuit statement, mirroring the "Prestação de contas" sheet."""

    entries: tuple[FinanceEntry, ...]
    paid_income: Decimal
    bank_fees: Decimal
    tax: Decimal
    net: Decimal
    partner_share: Decimal
    partner_paid: Decimal
    balance: Decimal
    future_income: Decimal
    partner_future: Decimal
    office_revenue: Decimal

    @property
    def has_activity(self) -> bool:
        return bool(self.entries)


def _round(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def account_case(entries: tuple[FinanceEntry, ...], percentage: Decimal) -> CaseAccount:
    """Net = paid − bank fees − 7.5% tax; partner share = net × percentage."""

    if not Decimal(0) <= percentage <= Decimal(100):
        raise ValueError("percentual da parceria fora do intervalo")
    rate = percentage / Decimal(100)

    def total(kind: EntryKind, *, paid: bool) -> Decimal:
        return sum(
            (
                entry.amount
                for entry in entries
                if entry.kind is kind and entry.amount is not None and entry.paid is paid
            ),
            Decimal(0),
        )

    paid_income = total(EntryKind.FEE_INCOME, paid=True)
    bank_fees = total(EntryKind.BANK_FEE, paid=True)
    tax = _round(paid_income * TAX_RATE)
    net = paid_income - bank_fees - tax
    partner_share = _round(net * rate)
    partner_paid = total(EntryKind.PARTNER_PAYOUT, paid=True)
    future_income = total(EntryKind.FEE_INCOME, paid=False)
    # Future installments are an estimate: bank fees are only known once paid.
    partner_future = _round(future_income * (1 - TAX_RATE) * rate)
    return CaseAccount(
        entries=tuple(
            sorted(
                entries,
                key=lambda entry: (
                    entry.date_payment or entry.date_due or date.max,
                    _DISPLAY_ORDER[entry.kind],
                ),
            )
        ),
        paid_income=paid_income,
        bank_fees=bank_fees,
        tax=tax,
        net=net,
        partner_share=partner_share,
        partner_paid=partner_paid,
        balance=partner_share - partner_paid,
        future_income=future_income,
        partner_future=partner_future,
        office_revenue=net - partner_share,
    )

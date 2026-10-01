"""Partner report in the office's model format (ADR-007): summary, clients, accounting."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from partner_reports.reports.financial import (
    FINANCE_RULE_VERSION,
    CaseAccount,
    FinanceEntry,
    account_case,
)

STAGE_RULE_VERSION = "stage-map-1"
_KNOWN_STEPS = frozenset(
    {
        "MARKETING",
        "NEGOCIAÇÃO",
        "CONSULTORIA",
        "ADMINISTRATIVO",
        "JUDICIAL",
        "RECURSAL",
        "EXECUÇÃO/COBRANÇA",
        "RH/FINANCEIRO",
        "ARQUIVAMENTO",
    }
)
_JUDICIAL_STEPS = frozenset({"JUDICIAL", "RECURSAL", "EXECUÇÃO/COBRANÇA"})
_AWAITING_FEES = "AGUARDANDO PAGAMENTO DOS HONORÁRIOS"
_FEES_SETTLED = "HONORÁRIOS QUITADOS"


def _normalized(value: str | None) -> str:
    return " ".join((value or "").upper().split())


@dataclass(frozen=True)
class StageFlags:
    known: bool
    judicial: bool
    benefit: bool
    awaiting_fees: bool


def classify_stage(step: str | None, stage: str | None) -> StageFlags:
    """Stage map confirmed on 01/10/2026 (docs/MAPA_MODELO_RELATORIO.md, section 4)."""

    step_name, stage_name = _normalized(step), _normalized(stage)
    return StageFlags(
        known=step_name in _KNOWN_STEPS,
        judicial=step_name in _JUDICIAL_STEPS,
        benefit=step_name == "EXECUÇÃO/COBRANÇA" or stage_name in {_AWAITING_FEES, _FEES_SETTLED},
        awaiting_fees=stage_name == _AWAITING_FEES,
    )


@dataclass(frozen=True)
class CaseInput:
    lawsuit_id: uuid.UUID
    customer_ids: tuple[uuid.UUID, ...]
    customer_names: tuple[str, ...]
    folder: str | None
    process_number: str | None
    action: str | None
    step: str | None
    stage: str | None
    responsible: str | None
    contingency: str | None
    fees_expected: Decimal | None
    last_movement_at: datetime | None
    last_movement_title: str | None
    entries: tuple[FinanceEntry, ...]


@dataclass(frozen=True)
class CaseView:
    source: CaseInput
    flags: StageFlags
    account: CaseAccount
    in_financial: bool


@dataclass(frozen=True)
class Indicators:
    clients: int
    cases: int
    benefit: int
    financial: int
    judicial: int
    unclassified: int


@dataclass(frozen=True)
class FinanceSummary:
    cases_with_finance: int
    paid_income: Decimal
    partner_share: Decimal
    partner_paid: Decimal
    balance: Decimal
    partner_future: Decimal
    office_revenue: Decimal


@dataclass(frozen=True)
class PartnerReport:
    partner_name: str
    period_start: date
    period_end: date
    as_of: datetime
    generated_at: datetime
    version: int
    percentage: Decimal
    indicators: Indicators
    finance: FinanceSummary
    cases: tuple[CaseView, ...]
    rule_version: str = f"{STAGE_RULE_VERSION}+{FINANCE_RULE_VERSION}"


def build_partner_report(
    *,
    partner_name: str,
    period_start: date,
    period_end: date,
    as_of: datetime,
    generated_at: datetime,
    version: int,
    percentage: Decimal,
    cases: tuple[CaseInput, ...],
) -> PartnerReport:
    if as_of.tzinfo is None or generated_at.tzinfo is None or generated_at < as_of:
        raise ValueError("instantes do relatório inválidos")
    if version < 1 or period_start > period_end:
        raise ValueError("versão ou período inválidos")
    views = []
    for case in sorted(
        cases, key=lambda item: ((item.customer_names or ("",))[0].casefold(), item.folder or "")
    ):
        flags = classify_stage(case.step, case.stage)
        account = account_case(case.entries, percentage)
        views.append(
            CaseView(
                source=case,
                flags=flags,
                account=account,
                in_financial=flags.awaiting_fees or account.future_income > 0,
            )
        )

    def total(field: str) -> Decimal:
        return sum((getattr(view.account, field) for view in views), Decimal(0))

    return PartnerReport(
        partner_name=partner_name,
        period_start=period_start,
        period_end=period_end,
        as_of=as_of,
        generated_at=generated_at,
        version=version,
        percentage=percentage,
        indicators=Indicators(
            clients=len({customer for case in cases for customer in case.customer_ids}),
            cases=len(views),
            benefit=sum(view.flags.benefit for view in views),
            financial=sum(view.in_financial for view in views),
            judicial=sum(view.flags.judicial for view in views),
            unclassified=sum(not view.flags.known for view in views),
        ),
        finance=FinanceSummary(
            cases_with_finance=sum(view.account.has_activity for view in views),
            paid_income=total("paid_income"),
            partner_share=total("partner_share"),
            partner_paid=total("partner_paid"),
            balance=total("balance"),
            partner_future=total("partner_future"),
            office_revenue=total("office_revenue"),
        ),
        cases=tuple(views),
    )

"""ADR-007 accounting and stage rules; synthetic values only."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from partner_reports.reports.financial import (
    EntryKind,
    FinanceEntry,
    account_case,
    classify_entry,
)
from partner_reports.reports.full_report import CaseInput, build_partner_report, classify_stage
from partner_reports.reports.partner_render import render_partner_report_html

AS_OF = datetime(2026, 10, 1, 12, tzinfo=UTC)


def _entry(kind: EntryKind, amount: str, *, paid: bool = True) -> FinanceEntry:
    return FinanceEntry(
        kind=kind,
        category="CATEGORIA SINTÉTICA",
        description="Parcela sintética",
        date_due=date(2026, 9, 5),
        date_payment=date(2026, 9, 5) if paid else None,
        amount=Decimal(amount),
    )


@pytest.mark.parametrize(
    ("entry_type", "category", "expected"),
    [
        ("income", "HONORÁRIOS POR MENSALIDADE", EntryKind.FEE_INCOME),
        ("income", "HONORÁRIO ADVOCATÍCIO - BPC/LOAS", EntryKind.FEE_INCOME),
        ("income", "1 - HONORÁRIOS ADVOCATÍCIOS", EntryKind.FEE_INCOME),
        ("income", "RPVS", EntryKind.FEE_INCOME),
        ("expense", "taxas  bancárias", EntryKind.BANK_FEE),
        ("expense", "HONORÁRIOS DE PARCEIROS", EntryKind.PARTNER_PAYOUT),
        ("expense", "SALÁRIOS", None),
        ("expense", "REPASSE DE RPV AO CLIENTE", None),
        ("income", "REEMBOLSO DE CUSTO POR CLIENTES", None),
        ("expense", "HONORÁRIOS DE ADVOGADOS ASSOCIADOS", None),
        (None, "HONORÁRIOS INICIAIS", None),
    ],
)
def test_only_accounting_categories_are_read(entry_type, category, expected) -> None:
    assert classify_entry(entry_type, category) is expected


def test_account_follows_office_model_formulas() -> None:
    account = account_case(
        (
            _entry(EntryKind.FEE_INCOME, "3240.00"),
            _entry(EntryKind.FEE_INCOME, "400.00"),
            _entry(EntryKind.BANK_FEE, "3.99"),
            _entry(EntryKind.BANK_FEE, "3.45"),
            _entry(EntryKind.PARTNER_PAYOUT, "500.00"),
            _entry(EntryKind.FEE_INCOME, "400.00", paid=False),
        ),
        Decimal("20.00"),
    )
    assert account.paid_income == Decimal("3640.00")
    assert account.bank_fees == Decimal("7.44")
    assert account.tax == Decimal("273.00")  # 7.5% of 3,640.00
    assert account.net == Decimal("3359.56")
    assert account.partner_share == Decimal("671.91")  # 20% of 3,359.56, half up
    assert account.partner_paid == Decimal("500.00")
    assert account.balance == Decimal("171.91")
    assert account.future_income == Decimal("400.00")
    assert account.partner_future == Decimal("74.00")  # 400 × 0.925 × 20%
    assert account.office_revenue == Decimal("2687.65")


def test_empty_account_is_zero_and_percentage_is_bounded() -> None:
    account = account_case((), Decimal("10"))
    assert not account.has_activity
    assert account.partner_share == Decimal("0") and account.balance == Decimal("0")
    with pytest.raises(ValueError, match="percentual"):
        account_case((), Decimal("100.01"))


@pytest.mark.parametrize(
    ("step", "stage", "known", "judicial", "benefit", "awaiting"),
    [
        ("ADMINISTRATIVO", "REQUERIMENTO PROTOCOLADO", True, False, False, False),
        ("JUDICIAL", "AGUARDANDO SENTENÇA", True, True, False, False),
        ("RECURSAL", "RECURSO JULGADO", True, True, False, False),
        ("EXECUÇÃO/COBRANÇA", "RPV EMITIDO", True, True, True, False),
        ("RH/FINANCEIRO", "AGUARDANDO PAGAMENTO DOS HONORÁRIOS", True, False, True, True),
        ("RH/FINANCEIRO", "HONORÁRIOS QUITADOS", True, False, True, False),
        ("RH/FINANCEIRO", "VENDA CONCLUÍDA - PAGAMENTO A VISTA", True, False, False, False),
        ("ARQUIVAMENTO", "ARQUIVADO/ENCERRADO", True, False, False, False),
        ("ETAPA NOVA", "FASE NOVA", False, False, False, False),
        (None, None, False, False, False, False),
    ],
)
def test_stage_map(step, stage, known, judicial, benefit, awaiting) -> None:
    flags = classify_stage(step, stage)
    assert (flags.known, flags.judicial, flags.benefit, flags.awaiting_fees) == (
        known,
        judicial,
        benefit,
        awaiting,
    )


def _case(step: str | None, stage: str | None, *customers: uuid.UUID, entries=()) -> CaseInput:
    return CaseInput(
        lawsuit_id=uuid.uuid4(),
        customer_ids=customers,
        customer_names=tuple(f"Cliente {index}" for index, _ in enumerate(customers)),
        folder="PASTA-SINTETICA",
        process_number="12345678920261234567",
        action="AÇÃO SINTÉTICA",
        step=step,
        stage=stage,
        responsible="Responsável Sintético",
        contingency=None,
        fees_expected=None,
        last_movement_at=AS_OF - timedelta(days=3),
        last_movement_title="<script>andamento</script>",
        entries=tuple(entries),
    )


def test_indicators_overlap_and_count_distinct_clients() -> None:
    shared = uuid.uuid4()
    report = build_partner_report(
        partner_name="Parceiro Sintético",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        as_of=AS_OF,
        generated_at=AS_OF + timedelta(minutes=1),
        version=1,
        percentage=Decimal("10.00"),
        cases=(
            _case("EXECUÇÃO/COBRANÇA", "RPV EMITIDO", shared),
            _case(
                "ADMINISTRATIVO",
                "AGUARDANDO DISTRIBUIÇÃO",
                shared,
                uuid.uuid4(),
                entries=(_entry(EntryKind.FEE_INCOME, "100.00", paid=False),),
            ),
            _case("ETAPA NOVA", "FASE NOVA", uuid.uuid4()),
        ),
    )
    indicators = report.indicators
    assert (indicators.clients, indicators.cases) == (3, 3)
    assert (indicators.judicial, indicators.benefit, indicators.financial) == (1, 1, 1)
    assert indicators.unclassified == 1
    assert report.finance.cases_with_finance == 1
    html = render_partner_report_html(report)
    assert "Parceiro Sintético" in html
    assert "1234567-89.2026.1.23.4567" in html
    assert "<script>andamento" not in html  # free text is escaped
    assert "10%" in html


def test_report_rejects_inconsistent_instants() -> None:
    with pytest.raises(ValueError):
        build_partner_report(
            partner_name="Parceiro Sintético",
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            as_of=AS_OF,
            generated_at=AS_OF - timedelta(seconds=1),
            version=1,
            percentage=Decimal("10"),
            cases=(),
        )


def test_partner_report_uses_the_light_identity() -> None:
    from importlib.resources import files

    css = files("partner_reports.reports").joinpath("assets/partner_report.css").read_text()
    # Reports are never shown on a dark primary background (decision of 02/10/2026).
    assert "color:var(--text);background:var(--white)" in css
    assert "--white:#FFFFFF" in css and "--text:#0A0A0A" in css
    assert "#EDEDED" not in css and "background:var(--black)" not in css

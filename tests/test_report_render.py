"""Synthetic rendering, conditional sections, and external privacy boundary."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from importlib.resources import files
from io import BytesIO

import pytest
from pypdf import PdfReader

import partner_reports.reports.render as renderer
from partner_reports.contracts.view_model import FinancialSummary, ReportValue
from partner_reports.reports.preview_cli import synthetic_preview
from partner_reports.reports.render import (
    UnsafeReportData,
    generate_pdf,
    render_html,
    to_partner_report,
)

AS_OF = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(("scenario", "expected_cases"), [("zero", 0), ("one", 1), ("many", 55)])
def test_html_renders_synthetic_portfolios_without_empty_sections(
    scenario: str, expected_cases: int
) -> None:
    internal = synthetic_preview(scenario)
    html = render_html(internal)
    assert "PRÉVIA SINTÉTICA" in html
    assert '<html lang="pt-BR">' in html
    assert f"{expected_cases} casos" in html
    assert "Resumo executivo" in html
    assert "Relatório v1" in html
    assert "METODOLOGIA" in html
    assert "R$ 0,00" not in html
    assert "Resumo financeiro" not in html
    assert "https://" not in html
    assert "<script" not in html
    if expected_cases == 0:
        assert "Nenhum processo elegível" in html
        assert '<table class="case-table">' not in html
    else:
        assert '<table class="case-table">' in html
        assert '<details class="case-detail">' in html
    if scenario == "many":
        assert html.count("<tr><td><strong>L-") == 55


def test_internal_identifiers_never_reach_template() -> None:
    internal = synthetic_preview("one")
    html = render_html(internal)
    assert str(internal.partner_id) not in html
    assert str(internal.linked_case_ids.value[0]) not in html
    assert "SYNTHETIC-ONE" in html


@pytest.mark.parametrize(
    "dangerous",
    [
        "CPF 123.456.789-09",
        "CNPJ 12.345.678/0001-90",
        "1234567-89.2026.1.01.0001",
        "senha: synthetic-secret",
        "Bearer synthetic-token",
        "diagnóstico sintético",
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
    ],
)
def test_sensitive_patterns_are_rejected_before_template(dangerous: str) -> None:
    internal = synthetic_preview("one")
    preview = internal.partner_preview
    assert preview is not None
    origin = ReportValue[str](status="available", value=dangerous, source="synthetic", as_of=AS_OF)
    tampered = internal.model_copy(
        update={"partner_preview": preview.model_copy(update={"origin": origin})}
    )
    with pytest.raises(UnsafeReportData):
        render_html(tampered)


def test_jinja_escapes_even_if_projection_gate_is_bypassed(monkeypatch: pytest.MonkeyPatch) -> None:
    internal = synthetic_preview("one")
    preview = internal.partner_preview
    assert preview is not None
    origin = ReportValue[str](
        status="available", value="SYNTHETIC <demo> & data", source="synthetic", as_of=AS_OF
    )
    tampered = internal.model_copy(
        update={"partner_preview": preview.model_copy(update={"origin": origin})}
    )
    with pytest.raises(UnsafeReportData):
        render_html(tampered)
    monkeypatch.setattr(renderer, "to_partner_report", lambda _: tampered.partner_preview)
    html = render_html(tampered)
    assert "SYNTHETIC &lt;demo&gt; &amp; data" in html
    assert "SYNTHETIC <demo>" not in html


def test_free_text_cannot_replace_controlled_reference() -> None:
    internal = synthetic_preview("one")
    preview = internal.partner_preview
    assert preview is not None
    case = preview.cases.value[0]
    free_text = ReportValue[str](
        status="available", value="Nome de pessoa sintética", source="synthetic", as_of=AS_OF
    )
    altered_case = case.model_copy(update={"reference": free_text})
    altered_cases = preview.cases.model_copy(update={"value": (altered_case,)})
    tampered = internal.model_copy(
        update={"partner_preview": preview.model_copy(update={"cases": altered_cases})}
    )
    with pytest.raises(UnsafeReportData):
        render_html(tampered)


def test_financial_card_requires_validated_approved_source() -> None:
    internal = synthetic_preview("one")
    preview = internal.partner_preview
    assert preview is not None
    amount = FinancialSummary(partner_due=Decimal("0.00"))
    unapproved = ReportValue[FinancialSummary](
        status="available", value=amount, source="synthetic", as_of=AS_OF
    )
    tampered = internal.model_copy(
        update={"partner_preview": preview.model_copy(update={"financial": unapproved})}
    )
    assert "R$ 0,00" not in render_html(tampered)
    approved = ReportValue[FinancialSummary](
        status="available",
        value=amount,
        source="approved_financial_rule",
        as_of=AS_OF,
        last_validated_at=AS_OF,
    )
    tampered = internal.model_copy(
        update={"partner_preview": preview.model_copy(update={"financial": approved})}
    )
    approved_html = render_html(tampered)
    assert "Resumo financeiro" in approved_html
    assert "R$ 0,00" in approved_html


def test_no_preview_cannot_be_projected() -> None:
    internal = synthetic_preview("zero").model_copy(update={"partner_preview": None})
    with pytest.raises(UnsafeReportData):
        to_partner_report(internal)


@pytest.mark.browser
def test_pdf_text_contains_only_safe_synthetic_projection() -> None:
    internal = synthetic_preview("one")
    preview = internal.partner_preview
    assert preview is not None
    forbidden = "Bearer SYNTHETIC_SECRET_NEVER_DISCLOSE"
    tampered = internal.model_copy(
        update={
            "partner_preview": preview.model_copy(
                update={
                    "origin": ReportValue[str](
                        status="available", value=forbidden, source="synthetic", as_of=AS_OF
                    )
                }
            )
        }
    )
    with pytest.raises(UnsafeReportData):
        asyncio.run(generate_pdf(tampered))
    pdf = asyncio.run(generate_pdf(internal))
    extracted = " ".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
    assert "SYNTHETIC-ONE" in extracted
    assert forbidden not in extracted
    assert str(internal.partner_id) not in extracted
    assert "senha" not in extracted.casefold()


def test_approved_palette_and_hover_token_scope() -> None:
    css = files("partner_reports.reports").joinpath("assets/report.css").read_text()
    for color in ("#F4AA27", "#FFC14D", "#0A0A0A", "#EDEDED"):
        assert color in css
    assert css.count("#FFC14D") == 1
    assert ".button-primary:hover{background:var(--gold-hover)" in css


@pytest.mark.browser
@pytest.mark.parametrize("scenario", ["zero", "one", "many"])
def test_chromium_generates_a4_pdf_from_same_synthetic_model(scenario: str) -> None:
    pdf = asyncio.run(generate_pdf(synthetic_preview(scenario)))
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 10_000


@pytest.mark.browser
@pytest.mark.parametrize("width", [375, 1280])
def test_html_has_no_page_level_horizontal_overflow(width: int) -> None:
    from playwright.async_api import async_playwright

    async def inspect() -> bool:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page(viewport={"width": width, "height": 900})
                await page.set_content(render_html(synthetic_preview("many")))
                return await page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth && "
                    "document.querySelector('.table-wrap').scrollWidth <= "
                    "document.querySelector('.table-wrap').clientWidth"
                )
            finally:
                await browser.close()

    assert asyncio.run(inspect())


@pytest.mark.browser
def test_palette_is_applied_in_browser() -> None:
    from playwright.async_api import async_playwright

    async def inspect() -> tuple[str, str, str, str, str]:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_content(render_html(synthetic_preview("one")))
                await page.locator(".sheet").evaluate(
                    "element => element.insertAdjacentHTML('beforeend', "
                    '\'<button class="button-primary" type="button">Abrir</button>\')'
                )
                base = await page.evaluate(
                    """() => [
                        getComputedStyle(document.documentElement).backgroundColor,
                        getComputedStyle(document.documentElement).color,
                        getComputedStyle(document.querySelector('h2')).color,
                        getComputedStyle(document.querySelector('.button-primary')).backgroundColor
                    ]"""
                )
                await page.locator(".button-primary").hover()
                hover = await page.locator(".button-primary").evaluate(
                    "element => getComputedStyle(element).backgroundColor"
                )
                return (*base, hover)
            finally:
                await browser.close()

    assert asyncio.run(inspect()) == (
        "rgb(10, 10, 10)",
        "rgb(237, 237, 237)",
        "rgb(244, 170, 39)",
        "rgb(244, 170, 39)",
        "rgb(255, 193, 77)",
    )

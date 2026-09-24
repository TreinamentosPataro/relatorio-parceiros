"""Privacy-gated Jinja2 HTML and Chromium PDF rendering from one view model."""

import re
from datetime import date, datetime
from decimal import Decimal
from importlib.resources import files
from typing import Any

from jinja2 import Environment, StrictUndefined, select_autoescape

from partner_reports.contracts.common import AvailabilityStatus
from partner_reports.contracts.view_model import InternalReportViewModel, ReportViewModel

_PARTNER_FIELDS = frozenset(
    {
        "partner",
        "metadata",
        "origin",
        "summary",
        "metrics",
        "distributions",
        "customers",
        "cases",
        "financial",
        "alerts",
        "publication_ready",
    }
)
_BLOCKED_PATTERNS = (
    re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)"),
    re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)"),
    re.compile(r"(?<!\d)\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}(?!\d)"),
    re.compile(r"\b(?:senha|password|token|bearer|api[_ -]?key|secret|segredo|cpf|cnpj)\b", re.I),
    re.compile(r"\b(?:diagn[oó]stico|doen[cç]a|sa[uú]de|medicamento|tratamento)\b", re.I),
    re.compile(r"(?:<\s*script|<\s*iframe|<\s*svg|<\s*img|javascript:|on\w+\s*=)", re.I),
    re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|eyJ[A-Za-z0-9_-]{16,}\.)"),
)
_ALERT_LABELS = {
    "missing_movement": "Processos sem andamento registrado",
    "missing_customer_reference": "Relações de cliente incompletas",
    "freshness_threshold_pending": "Critério de desatualização ainda não aprovado",
}
_CUSTOMER_REFERENCE = re.compile(r"C-\d{3,}")
_CASE_REFERENCE = re.compile(r"L-\d{3,}")


class UnsafeReportData(ValueError):
    """External projection contained a blocked or unclassified value."""


def _scan_strings(value: Any) -> None:
    if isinstance(value, str):
        if any(pattern.search(value) for pattern in _BLOCKED_PATTERNS):
            raise UnsafeReportData("conteúdo não permitido na visão externa")
    elif isinstance(value, dict):
        for key, item in value.items():
            _scan_strings(key)
            _scan_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _scan_strings(item)


def to_partner_report(internal: InternalReportViewModel) -> ReportViewModel:
    """Explicit allowlist boundary before any template sees report data."""

    if internal.partner_preview is None:
        raise UnsafeReportData("prévia indisponível: vínculo ou fonte não aprovado")
    payload = {key: getattr(internal.partner_preview, key) for key in _PARTNER_FIELDS}
    report = ReportViewModel.model_validate(payload)
    if report.publication_ready:
        raise UnsafeReportData("publicação não autorizada")
    _validate_external_semantics(report)
    _scan_strings(report.model_dump(mode="json"))
    return report


def _validate_external_semantics(report: ReportViewModel) -> None:
    """Fail closed while labels and legal classifications await business approval."""

    if (
        report.partner.status is not AvailabilityStatus.AVAILABLE
        or report.metadata.status is not AvailabilityStatus.AVAILABLE
        or report.origin.value != "advbox_normalized"
        or report.metadata.value.rule_version != "portfolio_snapshot_v1"
        or report.metrics.unique_customers.status is not AvailabilityStatus.AVAILABLE
        or report.metrics.lawsuits.status is not AvailabilityStatus.AVAILABLE
        or report.customers.status is not AvailabilityStatus.AVAILABLE
        or report.cases.status is not AvailabilityStatus.AVAILABLE
    ):
        raise UnsafeReportData("fonte ou campos obrigatórios não classificados")
    if any(
        value.status is AvailabilityStatus.AVAILABLE
        for value in (
            report.metrics.benefits_granted,
            report.metrics.in_financial,
            report.metrics.in_judicial,
            report.distributions.by_stage,
            report.distributions.by_legal_status,
            report.distributions.by_area,
        )
    ):
        raise UnsafeReportData("classificação de negócio ainda não aprovada")
    for customer in report.customers.value:
        if not _CUSTOMER_REFERENCE.fullmatch(customer.reference.value or ""):
            raise UnsafeReportData("referência de cliente não classificada")
        if customer.lawsuit_references.status is not AvailabilityStatus.AVAILABLE or any(
            not _CASE_REFERENCE.fullmatch(reference)
            for reference in customer.lawsuit_references.value or ()
        ):
            raise UnsafeReportData("associação de cliente não classificada")
    for case in report.cases.value:
        if not _CASE_REFERENCE.fullmatch(case.reference.value or ""):
            raise UnsafeReportData("referência de processo não classificada")
        if case.customer_references.status is not AvailabilityStatus.AVAILABLE or any(
            not _CUSTOMER_REFERENCE.fullmatch(reference)
            for reference in case.customer_references.value or ()
        ):
            raise UnsafeReportData("associação de processo não classificada")
        if case.executive_status.status is AvailabilityStatus.AVAILABLE:
            raise UnsafeReportData("status executivo ainda não aprovado")


def _date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _datetime(value: datetime) -> str:
    return value.strftime("%d/%m/%Y %H:%M %Z").strip()


def _money(value: Decimal) -> str:
    formatted = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {formatted}"


def _context(report: ReportViewModel) -> dict[str, Any]:
    metadata = report.metadata.value
    assert metadata is not None
    metrics = report.metrics
    cases = report.cases.value or ()
    customers = report.customers.value or ()
    alerts = report.alerts.value or ()
    available_distributions = (
        ("Fases", report.distributions.by_stage),
        ("Status jurídicos", report.distributions.by_legal_status),
        ("Áreas", report.distributions.by_area),
    )
    distributions = []
    for label, field in available_distributions:
        values = field.value
        if field.status is not AvailabilityStatus.AVAILABLE or not values or len(values) < 2:
            continue
        total = sum(values.values())
        if total <= 0:
            continue
        distributions.append(
            {
                "label": label,
                "items": [
                    {"label": key, "count": count, "percent": round(100 * count / total)}
                    for key, count in sorted(values.items())
                ],
            }
        )
    financial = report.financial
    financial_visible = (
        financial.status is AvailabilityStatus.AVAILABLE
        and financial.value is not None
        and financial.last_validated_at is not None
        and financial.source == "approved_financial_rule"
    )
    unknown_alerts = {alert.code for alert in alerts} - _ALERT_LABELS.keys()
    if unknown_alerts:
        raise UnsafeReportData("alerta sem classificação externa")
    return {
        "partner_code": report.partner.value.code,
        "period_start": _date(metadata.period_start),
        "period_end": _date(metadata.period_end),
        "updated_at": _datetime(metadata.as_of),
        "generated_at": _datetime(metadata.generated_at),
        "version": metadata.report_version,
        "rule_version": metadata.rule_version,
        "customer_count": metrics.unique_customers.value,
        "case_count": metrics.lawsuits.value,
        "cases": [
            {
                "reference": case.reference.value,
                "customers": ", ".join(case.customer_references.value or ()),
                "movement_date": (
                    _datetime(case.latest_recorded_movement_at.value)
                    if case.latest_recorded_movement_at.value is not None
                    else None
                ),
                "executive_status": (
                    case.executive_status.value
                    if case.executive_status.status is AvailabilityStatus.AVAILABLE
                    else None
                ),
            }
            for case in cases
        ],
        "customers": [
            {
                "reference": customer.reference.value,
                "cases": ", ".join(customer.lawsuit_references.value or ()),
            }
            for customer in customers
        ],
        "alerts": [
            {
                "code": alert.code,
                "label": _ALERT_LABELS[alert.code],
                "count": alert.count.value,
                "available": alert.count.status is AvailabilityStatus.AVAILABLE,
            }
            for alert in alerts
        ],
        "distributions": distributions,
        "financial_visible": financial_visible,
        "financial_amount": _money(financial.value.partner_due) if financial_visible else None,
        "financial_validated_at": (
            _datetime(financial.last_validated_at) if financial_visible else None
        ),
        "origin": report.origin.value,
    }


def render_html(internal: InternalReportViewModel) -> str:
    """Return self-contained responsive HTML; never render the internal model directly."""

    report = to_partner_report(internal)
    root = files("partner_reports.reports")
    template_text = root.joinpath("templates/report.html.j2").read_text(encoding="utf-8")
    css = root.joinpath("assets/report.css").read_text(encoding="utf-8")
    environment = Environment(
        autoescape=select_autoescape(enabled_extensions=("html", "j2"), default=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return environment.from_string(template_text).render(**_context(report), css=css)


async def generate_pdf(
    internal: InternalReportViewModel, *, executable_path: str | None = None
) -> bytes:
    """Generate A4 bytes in Chromium; caller owns durable storage and access control."""

    from playwright.async_api import async_playwright

    html = render_html(internal)
    report = to_partner_report(internal)
    version = report.metadata.value.report_version
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            executable_path=executable_path,
        )
        try:
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            await page.route("**/*", lambda route: route.abort())
            await page.set_content(html, wait_until="load")
            pdf = await page.pdf(
                format="A4",
                scale=0.94,
                print_background=True,
                prefer_css_page_size=True,
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=(
                    '<div style="box-sizing:border-box;width:100%;height:15mm;'
                    "font:9px Arial,sans-serif;color:#EDEDED;background:#0A0A0A;"
                    "-webkit-print-color-adjust:exact;print-color-adjust:exact;"
                    'padding:3mm 16mm 0;display:flex;justify-content:space-between">'
                    f"<span>Prévia sintética · versão {version}</span>"
                    '<span><span class="pageNumber"></span> / '
                    '<span class="totalPages"></span></span></div>'
                ),
                margin={"top": "10mm", "right": "16mm", "bottom": "15mm", "left": "16mm"},
            )
            if not pdf.startswith(b"%PDF"):
                raise RuntimeError("Chromium não produziu PDF válido")
            return pdf
        finally:
            await browser.close()

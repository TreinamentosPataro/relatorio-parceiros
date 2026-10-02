"""HTML and A4 PDF for the partner report in the office model format (ADR-007)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from importlib.resources import files
from zoneinfo import ZoneInfo

from jinja2 import Environment, StrictUndefined, select_autoescape

from partner_reports.reports.financial import EntryKind
from partner_reports.reports.full_report import PartnerReport
from partner_reports.reports.render import html_to_pdf

_ZONE = ZoneInfo("America/Sao_Paulo")
_KIND_LABELS = {
    EntryKind.FEE_INCOME: "Honorário",
    EntryKind.BANK_FEE: "Taxa",
    EntryKind.PARTNER_PAYOUT: "Repasse",
}


def _money(value: Decimal) -> str:
    text = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if value < 0 else ''}R$ {text}"


def _percent(value: Decimal) -> str:
    return f"{value.normalize():f}".replace(".", ",") + "%"


def _date(value: date | datetime | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        value = (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(_ZONE)
    return value.strftime("%d/%m/%Y")


def _datetime(value: datetime) -> str:
    return (
        (value if value.tzinfo else value.replace(tzinfo=UTC))
        .astimezone(_ZONE)
        .strftime("%d/%m/%Y %H:%M")
    )


def _cnj(value: str | None) -> str | None:
    if value and len(value) == 20 and value.isdigit():
        return f"{value[:7]}-{value[7:9]}.{value[9:13]}.{value[13]}.{value[14:16]}.{value[16:]}"
    return value


def render_partner_report_html(report: PartnerReport) -> str:
    root = files("partner_reports.reports")
    environment = Environment(
        autoescape=select_autoescape(default=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters.update(
        dinheiro=_money,
        percentual=_percent,
        data=_date,
        datahora=_datetime,
        cnj=_cnj,
        tipo=lambda kind: _KIND_LABELS[EntryKind(kind)],
    )
    template = root.joinpath("templates/partner_report.html.j2").read_text(encoding="utf-8")
    css = root.joinpath("assets/partner_report.css").read_text(encoding="utf-8")
    return environment.from_string(template).render(report=report, css=css)


async def generate_partner_report_pdf(
    report: PartnerReport, *, executable_path: str | None = None
) -> bytes:
    return await html_to_pdf(
        render_partner_report_html(report),
        footer_label=f"{report.partner_name} · versão {report.version}",
        executable_path=executable_path,
    )

"""CLI for the complete, count-only Advbox partner-linkage validation."""

import asyncio
from pathlib import Path

from pydantic import ValidationError

from partner_reports.integrations.advbox.client import AdvboxAuditClient, AdvboxAuditError
from partner_reports.integrations.advbox.config import AdvboxAuditSettings
from partner_reports.integrations.advbox.linkage_audit import FullPortfolioLinkageAuditor
from partner_reports.integrations.advbox.linkage_report import write_full_linkage_audit


async def _run() -> int:
    try:
        settings = AdvboxAuditSettings()  # type: ignore[call-arg]
    except ValidationError:
        print("Validação não executada: configuração local inválida ou ausente.")
        return 2

    try:
        async with AdvboxAuditClient(settings) as client:
            result = await FullPortfolioLinkageAuditor(client).run()
    except AdvboxAuditError as exc:
        print(f"Validação interrompida com erro seguro: {exc}")
        return 3

    output = Path("docs/VINCULO_PARCEIRO_CARTEIRA_VALIDACAO.md")
    write_full_linkage_audit(result, output)
    validation = result.validation_without_mapping
    print("Validação integral concluída em modo GET-only.")
    print(
        f"customers: total={result.customers.total}; páginas={result.customers.pages}; "
        f"campo_direto={result.customers.direct_partner_fields}"
    )
    print(
        f"lawsuits: total={result.lawsuits.total}; páginas={result.lawsuits.pages}; "
        f"campo_direto={result.lawsuits.direct_partner_fields}"
    )
    print(
        f"vínculos: vinculados={validation.lawsuits.linked}; "
        f"sem_vínculo={validation.lawsuits.unlinked}; "
        f"múltiplos={validation.lawsuits.multiple}; "
        f"referências_inexistentes={validation.nonexistent_references}"
    )
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())

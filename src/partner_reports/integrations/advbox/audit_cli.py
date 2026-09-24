"""Command-line entry point for the isolated, read-only Advbox audit."""

import argparse
import asyncio
from pathlib import Path

from pydantic import ValidationError

from partner_reports.integrations.advbox.audit import AdvboxAuditRunner
from partner_reports.integrations.advbox.client import AdvboxAuditClient
from partner_reports.integrations.advbox.config import AdvboxAuditSettings
from partner_reports.integrations.advbox.report import write_sanitized_reports


async def _run(output_directory: Path) -> int:
    try:
        settings = AdvboxAuditSettings()  # type: ignore[call-arg]
    except ValidationError:
        print("Auditoria não executada: configure ADVBOX_API_TOKEN apenas no .env local.")
        return 2

    async with AdvboxAuditClient(settings) as client:
        result = await AdvboxAuditRunner(client).run()
    write_sanitized_reports(result, output_directory)

    print("Auditoria Advbox concluída em modo GET-only.")
    for observation in result.observations:
        status = observation.status_code if observation.status_code is not None else "falha segura"
        duration = observation.duration_ms if observation.duration_ms is not None else "—"
        count = observation.item_count if observation.item_count is not None else "—"
        print(f"{observation.resource}: HTTP={status}; duração_ms={duration}; itens={count}")
    print(f"Vínculo parceiro–carteira: {result.linkage_status.value}")
    return 0


def main() -> int:
    """Parse safe output location and run the auditor."""

    parser = argparse.ArgumentParser(description="Auditoria GET-only da API Advbox")
    parser.add_argument("--output-dir", type=Path, default=Path("docs"))
    arguments = parser.parse_args()
    return asyncio.run(_run(arguments.output_dir))


if __name__ == "__main__":
    raise SystemExit(main())

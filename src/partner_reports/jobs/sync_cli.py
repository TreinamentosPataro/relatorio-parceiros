"""Safe operator CLI: only aggregate output, never payloads or credentials."""

import argparse
import asyncio
import json
import re
import time
import uuid

from partner_reports.integrations.advbox.client import AdvboxClient
from partner_reports.integrations.advbox.config import AdvboxAuditSettings
from partner_reports.jobs.sync import RESOURCES, SyncFailure, SyncRunner
from partner_reports.persistence.database import get_session_factory


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincronização Advbox GET-only")
    parser.add_argument("command", choices=("dry-run", "initial", "incremental", "reprocess"))
    parser.add_argument("--batch-key", help="chave técnica para retomar/reprocessar o mesmo lote")
    parser.add_argument("--resource", choices=RESOURCES, action="append")
    parser.add_argument("--max-pages", type=int, help="limitar páginas por recurso nesta execução")
    args = parser.parse_args()
    if args.command == "reprocess" and not args.batch_key:
        parser.error("reprocess exige --batch-key")
    batch_key = args.batch_key or uuid.uuid4().hex
    if len(batch_key) > 95 or not re.fullmatch(r"[A-Za-z0-9_-]+", batch_key):
        parser.error("--batch-key deve conter até 95 letras, números, _ ou -")
    if args.max_pages is not None and args.max_pages < 1:
        parser.error("--max-pages deve ser positivo")
    resources = args.resource or list(RESOURCES)
    print(json.dumps({"batch_key": batch_key, "command": args.command}))

    async def execute() -> int:
        started_at = time.monotonic()
        settings = AdvboxAuditSettings()  # type: ignore[call-arg]
        async with AdvboxClient(settings) as client:
            runner = SyncRunner(client, get_session_factory())
            for resource in resources:
                try:
                    summary = await runner.run_resource(
                        resource,
                        batch_key=batch_key,
                        dry_run=args.command == "dry-run",
                        reprocess=args.command == "reprocess",
                        max_pages=args.max_pages,
                    )
                except SyncFailure as error:
                    print(
                        json.dumps({"resource": resource, "status": "failed", "error": str(error)})
                    )
                    _print_transport_summary(client, started_at)
                    return 1
                print(json.dumps(summary.__dict__, sort_keys=True))
            _print_transport_summary(client, started_at)
        return 0

    return asyncio.run(execute())


def _print_transport_summary(client: AdvboxClient, started_at: float) -> None:
    metrics = client.metrics
    print(
        json.dumps(
            {
                "event": "transport_summary",
                "duration_ms": round((time.monotonic() - started_at) * 1000),
                "requests": metrics.requests,
                "http_429": metrics.http_429,
                "http_5xx": metrics.http_5xx,
                "transport_errors": metrics.transport_errors,
                "response_duration_ms": metrics.response_duration_ms,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

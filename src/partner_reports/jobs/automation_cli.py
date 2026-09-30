"""Operational commands for report jobs and scoped PDF processing."""

import argparse
import asyncio
import uuid
from pathlib import Path

from partner_reports.config import AppEnvironment, get_settings
from partner_reports.integrations.advbox.client import AdvboxClient
from partner_reports.integrations.advbox.config import AdvboxAuditSettings
from partner_reports.jobs.automation import (
    bump_revision,
    enqueue_cycle,
    process_one,
    retry_failed,
    scheduled_key,
    status,
)
from partner_reports.pdf_imports.automation import (
    pdf_import_status,
    process_one_pdf_import,
    retry_failed_pdf_imports,
)
from partner_reports.pdf_imports.storage import build_pdf_storage
from partner_reports.persistence.database import get_session_factory

# Bounded per scheduled run so one oneshot never monopolizes the single-vCPU host.
_DRAIN_LIMIT = 10


async def _drain(
    sessions, app_env: AppEnvironment, output_root: Path, limit: int = 100
) -> dict[str, int]:
    counts = {"succeeded": 0, "failed": 0}
    for _ in range(limit):
        result = await process_one(sessions, app_env, output_root)
        if result == "empty":
            break
        counts[result] += 1
    return counts


async def _process_private_work(settings, sessions, output_root: Path) -> str:
    api_settings = AdvboxAuditSettings()  # type: ignore[call-arg]
    storage = build_pdf_storage(settings.pdf_storage_root, settings.app_env)
    async with AdvboxClient(api_settings) as client:
        result = await process_one_pdf_import(sessions, settings, storage, client)
    if result != "empty":
        return f"import:{result}"
    return f"report:{await process_one(sessions, settings.app_env, output_root, settings=settings)}"


async def _drain_private(settings, sessions, output_root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for _ in range(_DRAIN_LIMIT):
        result = await _process_private_work(settings, sessions, output_root)
        if result == "report:empty":
            break
        counts[result] = counts.get(result, 0) + 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Automação de relatórios e importações PDF")
    parser.add_argument(
        "command",
        choices=(
            "run-now",
            "work-once",
            "drain",
            "worker-loop",
            "status",
            "retry-failed",
            "bump-revision",
        ),
    )
    parser.add_argument("--key", help="Chave idempotente do ciclo manual")
    parser.add_argument("--partner-code", help="Código SYNTHETIC-* para simular mudança")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    settings = get_settings()
    sessions = get_session_factory()
    output_root = args.output_root or settings.report_storage_root
    if not settings.synthetic_validation_only:
        if args.command == "work-once":
            print(f"job: {asyncio.run(_process_private_work(settings, sessions, output_root))}")
            return
        if args.command == "drain":
            print(f"jobs: {asyncio.run(_drain_private(settings, sessions, output_root))}")
            return
        if args.command == "status":
            print(f"importações: {pdf_import_status(sessions, settings)}")
            print(f"relatórios: {status(sessions, settings.app_env, settings)}")
            return
        if args.command == "retry-failed":
            print(f"importações reenfileiradas: {retry_failed_pdf_imports(sessions, settings)}")
            print(
                f"relatórios reenfileirados: {retry_failed(sessions, settings.app_env, settings)}"
            )
            return
        if args.command == "worker-loop":
            print("Worker privado iniciado; interrompa com Ctrl+C.", flush=True)
            try:
                while True:
                    asyncio.run(_process_private_work(settings, sessions, output_root))
                    asyncio.run(asyncio.sleep(30))
            except KeyboardInterrupt:
                print("Worker privado interrompido.")
            return
        parser.error("Comando disponível somente no escopo sintético")
    if args.command == "run-now":
        result = enqueue_cycle(sessions, settings.app_env, args.key or f"manual-{uuid.uuid4().hex}")
        print(f"ciclo: {result}")
        print(f"jobs: {asyncio.run(_drain(sessions, settings.app_env, output_root))}")
    elif args.command == "work-once":
        print(f"job: {asyncio.run(process_one(sessions, settings.app_env, output_root))}")
    elif args.command == "drain":
        print(f"jobs: {asyncio.run(_drain(sessions, settings.app_env, output_root, _DRAIN_LIMIT))}")
    elif args.command == "worker-loop":
        print("Worker local sintético iniciado; interrompa com Ctrl+C.", flush=True)
        try:
            while True:
                enqueue_cycle(sessions, settings.app_env, scheduled_key())
                asyncio.run(process_one(sessions, settings.app_env, output_root))
                asyncio.run(asyncio.sleep(30))
        except KeyboardInterrupt:
            print("Worker local interrompido.")
    elif args.command == "status":
        print(f"solicitações: {status(sessions, settings.app_env)}")
    elif args.command == "retry-failed":
        print(f"falhas reenfileiradas: {retry_failed(sessions, settings.app_env)}")
    elif args.command == "bump-revision":
        if not args.partner_code:
            parser.error("--partner-code é obrigatório")
        print(f"revisão sintética: {bump_revision(sessions, settings.app_env, args.partner_code)}")


if __name__ == "__main__":
    main()

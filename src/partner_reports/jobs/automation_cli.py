"""Local operational commands for the stage-9 synthetic worker."""

import argparse
import asyncio
import uuid
from pathlib import Path

from partner_reports.config import AppEnvironment, get_settings
from partner_reports.jobs.automation import (
    bump_revision,
    enqueue_cycle,
    process_one,
    retry_failed,
    scheduled_key,
    status,
)
from partner_reports.persistence.database import get_session_factory


async def _drain(sessions, app_env: AppEnvironment, output_root: Path) -> dict[str, int]:
    counts = {"succeeded": 0, "failed": 0}
    for _ in range(100):
        result = await process_one(sessions, app_env, output_root)
        if result == "empty":
            break
        counts[result] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Automação local exclusivamente sintética")
    parser.add_argument(
        "command",
        choices=("run-now", "work-once", "worker-loop", "status", "retry-failed", "bump-revision"),
    )
    parser.add_argument("--key", help="Chave idempotente do ciclo manual")
    parser.add_argument("--partner-code", help="Código SYNTHETIC-* para simular mudança")
    parser.add_argument("--output-root", type=Path, default=Path("output"))
    args = parser.parse_args()
    settings = get_settings()
    if settings.app_env is not AppEnvironment.DEVELOPMENT:
        parser.error("Comando operacional permitido apenas em desenvolvimento local")
    sessions = get_session_factory()
    if args.command == "run-now":
        result = enqueue_cycle(sessions, settings.app_env, args.key or f"manual-{uuid.uuid4().hex}")
        print(f"ciclo: {result}")
        print(f"jobs: {asyncio.run(_drain(sessions, settings.app_env, args.output_root))}")
    elif args.command == "work-once":
        print(f"job: {asyncio.run(process_one(sessions, settings.app_env, args.output_root))}")
    elif args.command == "worker-loop":
        print("Worker local sintético iniciado; interrompa com Ctrl+C.", flush=True)
        try:
            while True:
                enqueue_cycle(sessions, settings.app_env, scheduled_key())
                asyncio.run(process_one(sessions, settings.app_env, args.output_root))
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

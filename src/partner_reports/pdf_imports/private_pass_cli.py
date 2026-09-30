"""Explicitly authorized local second pass for PDF-7."""

import argparse
import asyncio
import json
from pathlib import Path

from pydantic import ValidationError

from partner_reports.config import AppEnvironment, Settings
from partner_reports.integrations.advbox.client import AdvboxAuditError, AdvboxClient
from partner_reports.integrations.advbox.config import AdvboxAuditSettings
from partner_reports.pdf_imports.homologation_cli import _safe_failure_code
from partner_reports.pdf_imports.private_pass import (
    persist_private_pass,
    prepare_private_pass,
    render_private_preview,
    write_private_preview,
)
from partner_reports.pdf_imports.storage import LocalPrivatePdfStorage
from partner_reports.persistence.database import get_session_factory


def main() -> int:
    parser = argparse.ArgumentParser(description="Segunda passagem privada autorizada do PDF-7")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--preview-dir", type=Path, required=True)
    args = parser.parse_args()

    async def execute() -> int:
        try:
            app_settings = Settings()  # type: ignore[call-arg]
            audit_settings = AdvboxAuditSettings()  # type: ignore[call-arg]
        except ValidationError:
            print(json.dumps({"status": "blocked", "code": "PDF7_CONFIGURATION_INVALID"}))
            return 2
        if app_settings.app_env is not AppEnvironment.DEVELOPMENT:
            print(json.dumps({"status": "blocked", "code": "PDF7_PRIVATE_ENVIRONMENT_BLOCKED"}))
            return 2
        try:
            async with AdvboxClient(audit_settings) as client:
                prepared = await prepare_private_pass(args.input_dir, client)
                html, pdf = await render_private_preview(prepared)
                transport = {
                    "requests": client.metrics.requests,
                    "http_429": client.metrics.http_429,
                    "http_5xx": client.metrics.http_5xx,
                    "transport_errors": client.metrics.transport_errors,
                }
            storage = LocalPrivatePdfStorage(app_settings.pdf_storage_root, app_settings.app_env)
            sessions = get_session_factory()
            with sessions() as db, db.begin():
                persistence = persist_private_pass(
                    db,
                    storage,
                    args.input_dir,
                    prepared,
                    environment=app_settings.app_env,
                )
            write_private_preview(args.preview_dir, html, pdf)
        except (AdvboxAuditError, OSError, ValueError) as exc:
            failure = {"status": "blocked", "code": _safe_failure_code(exc)}
            print(json.dumps(failure, sort_keys=True))
            return 1
        totals = {
            key: sum(summary[key] for summary in prepared.summaries)
            for key in prepared.summaries[0]
        }
        print(
            json.dumps(
                {
                    "status": "completed",
                    "mode": "pdf7_authorized_private_persistence",
                    "corpus": {
                        "source_files": prepared.corpus.source_files,
                        "page_count": prepared.corpus.page_count,
                        "manifest_items": prepared.corpus.manifest_items,
                    },
                    "api_snapshot": {"lawsuits": prepared.snapshot.total, "verified_reads": 2},
                    "reconciliation": totals,
                    "persistence": persistence,
                    "preview": {"generated": 1, "published": 0},
                    "transport": transport,
                },
                sort_keys=True,
            )
        )
        return 0

    return asyncio.run(execute())


if __name__ == "__main__":
    raise SystemExit(main())

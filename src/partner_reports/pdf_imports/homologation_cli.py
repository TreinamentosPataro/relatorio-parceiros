"""Safe command-line entry point for the first PDF-7 pass."""

import argparse
import asyncio
import json
from pathlib import Path

from pydantic import ValidationError

from partner_reports.integrations.advbox.client import (
    AdvboxAuditError,
    AdvboxAuthenticationError,
    AdvboxClient,
    AdvboxForbiddenError,
    AdvboxRateLimitError,
    AdvboxServerError,
    AdvboxTransportError,
    AdvboxUnexpectedResponse,
)
from partner_reports.integrations.advbox.config import AdvboxAuditSettings
from partner_reports.pdf_imports.homologation import execute_private_dry_run


def _safe_failure_code(exc: Exception) -> str:
    if isinstance(exc, AdvboxAuthenticationError):
        return "ADVBOX_AUTHENTICATION_FAILED"
    if isinstance(exc, AdvboxForbiddenError):
        return "ADVBOX_ACCESS_FORBIDDEN"
    if isinstance(exc, AdvboxRateLimitError):
        return "ADVBOX_RATE_LIMITED"
    if isinstance(exc, AdvboxServerError):
        return "ADVBOX_SERVER_FAILED"
    if isinstance(exc, AdvboxTransportError):
        return "ADVBOX_TRANSPORT_FAILED"
    if isinstance(exc, AdvboxUnexpectedResponse):
        if str(exc) in {"totalCount mudou durante a fotografia", "totalCount mudou entre leituras"}:
            return "ADVBOX_SNAPSHOT_TOTAL_CHANGED"
        if str(exc) == "origem mudou entre leituras":
            return "ADVBOX_SNAPSHOT_CONTENT_CHANGED"
        return "ADVBOX_CONTRACT_CHANGED"
    if str(exc).startswith("PDF7_"):
        return str(exc)
    return "PDF7_DRY_RUN_FAILED"


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run privado e count-only do PDF-7")
    parser.add_argument("--input-dir", type=Path, required=True)
    args = parser.parse_args()

    async def execute() -> int:
        try:
            settings = AdvboxAuditSettings()  # type: ignore[call-arg]
        except ValidationError:
            print(json.dumps({"status": "blocked", "code": "ADVBOX_TOKEN_UNAVAILABLE"}))
            return 2
        try:
            async with AdvboxClient(settings) as client:
                result = await execute_private_dry_run(args.input_dir, client)
                result["transport"] = {
                    "requests": client.metrics.requests,
                    "http_429": client.metrics.http_429,
                    "http_5xx": client.metrics.http_5xx,
                    "transport_errors": client.metrics.transport_errors,
                    "response_duration_ms": client.metrics.response_duration_ms,
                }
        except (AdvboxAuditError, OSError, ValueError) as exc:
            code = _safe_failure_code(exc)
            print(json.dumps({"status": "blocked", "code": code}, sort_keys=True))
            return 1
        print(json.dumps({"status": "completed", **result}, sort_keys=True))
        return 0

    return asyncio.run(execute())


if __name__ == "__main__":
    raise SystemExit(main())

"""Full count-only homologation dry-run with no API payload persistence."""

import asyncio
import json
import time
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select

from partner_reports.integrations.advbox.client import AdvboxClient
from partner_reports.integrations.advbox.config import AdvboxAuditSettings
from partner_reports.jobs.homologation import (
    HomologationDryRun,
    MappingReference,
)
from partner_reports.persistence.database import get_session_factory
from partner_reports.persistence.models import Partner, PartnerCaseLink


def _local_governance(reference_date: date) -> tuple[set[str], tuple[MappingReference, ...]]:
    with get_session_factory()() as session:
        partners = session.execute(
            select(Partner.id, Partner.external_id).where(
                Partner.status == "active", ~Partner.external_id.like("SYNTHETIC-%")
            )
        ).all()
        partner_keys = {str(partner_id): external_id for partner_id, external_id in partners}
        if not partner_keys:
            return set(), ()
        links = session.execute(
            select(
                PartnerCaseLink.advbox_entity_type,
                PartnerCaseLink.advbox_entity_id,
                PartnerCaseLink.partner_id,
            ).where(
                PartnerCaseLink.partner_id.in_(partner_keys),
                PartnerCaseLink.status == "active",
                PartnerCaseLink.valid_from <= reference_date,
                (PartnerCaseLink.valid_to.is_(None)) | (PartnerCaseLink.valid_to >= reference_date),
            )
        ).all()
    return set(partner_keys), tuple(
        MappingReference(entity_type, entity_id, str(partner_id))
        for entity_type, entity_id, partner_id in links
    )


def main() -> int:
    run_id = uuid.uuid4().hex

    async def execute() -> int:
        started_at = time.monotonic()
        started_utc = datetime.now(UTC)
        settings = AdvboxAuditSettings()  # type: ignore[call-arg]
        async with AdvboxClient(settings) as client:
            snapshot = await HomologationDryRun(client).run()
            reference_date = date.today()
            partner_keys, mappings = _local_governance(reference_date)
            summary = snapshot.public_summary(
                partner_keys=partner_keys,
                mappings=mappings,
                as_of=reference_date,
            )
            metrics = client.metrics
            summary.update(
                {
                    "run": {
                        "id": run_id,
                        "mode": "dry_run_no_persistence",
                        "started_utc": started_utc.isoformat(),
                        "finished_utc": datetime.now(UTC).isoformat(),
                        "duration_ms": round((time.monotonic() - started_at) * 1000),
                    },
                    "transport": {
                        "requests": metrics.requests,
                        "http_429": metrics.http_429,
                        "http_5xx": metrics.http_5xx,
                        "transport_errors": metrics.transport_errors,
                        "response_duration_ms": metrics.response_duration_ms,
                    },
                    "gate": {
                        "approved_mapping_available": bool(partner_keys and mappings),
                        "real_load_authorized": False,
                        "reports_generated": 0,
                        "reports_no_data": 0,
                        "reports_outdated": 0,
                        "reports_error": 0,
                    },
                }
            )
        print(json.dumps(summary, sort_keys=True))
        return 0

    return asyncio.run(execute())


if __name__ == "__main__":
    raise SystemExit(main())

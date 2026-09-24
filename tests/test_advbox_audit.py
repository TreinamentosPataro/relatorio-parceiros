"""Synthetic-only tests for schema sanitization and linkage classification."""

from datetime import UTC, datetime

from partner_reports.integrations.advbox.audit import (
    AuditRunResult,
    LinkageStatus,
    classify_linkage,
    sanitize_payload,
)
from partner_reports.integrations.advbox.report import render_api_audit, render_linkage_report


def test_sanitizer_keeps_structure_but_discards_values() -> None:
    sensitive_values = (
        "SYNTHETIC_PERSON_ALPHA",
        "synthetic.person@example.invalid",
        "00000000000",
        "+5500000000000",
        "SYNTHETIC_PRIVATE_NOTE",
    )
    payload = {
        "totalCount": 1,
        "limit": 1,
        "offset": 0,
        "data": [
            {
                "id": 77,
                "name": sensitive_values[0],
                "email": sensitive_values[1],
                "cpf": sensitive_values[2],
                "phone": sensitive_values[3],
                "notes": sensitive_values[4],
                "partner_id": 9,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": None,
            }
        ],
    }

    observation = sanitize_payload(
        resource="customers",
        endpoint_template="/customers",
        status_code=200,
        duration_ms=12,
        payload=payload,
    )

    serialized = repr(observation)
    assert all(value not in serialized for value in sensitive_values)
    assert "data[].partner_id" in observation.partner_candidate_fields
    assert "data[].id" in observation.id_fields
    assert "data[].created_at" in observation.date_fields
    assert "data[].updated_at" in observation.null_fields
    assert observation.pagination is not None
    assert observation.pagination.total_count == 1


def test_direct_partner_field_confirms_linkage() -> None:
    observation = sanitize_payload(
        resource="lawsuits",
        endpoint_template="/lawsuits",
        status_code=200,
        duration_ms=1,
        payload={"data": [{"partner_id": 3}], "limit": 1, "offset": 0},
    )

    status, evidence = classify_linkage([observation])

    assert status is LinkageStatus.CONFIRMADO
    assert evidence == ("lawsuits: data[].partner_id",)


def test_settings_partner_field_alone_does_not_confirm_linkage() -> None:
    observation = sanitize_payload(
        resource="settings",
        endpoint_template="/settings",
        status_code=200,
        duration_ms=1,
        payload={"partners": [{"id": 3}]},
    )

    status, _ = classify_linkage([observation])

    assert status is LinkageStatus.INCONCLUSIVO


def test_indirect_candidate_does_not_confirm_linkage() -> None:
    observations = [
        sanitize_payload(
            resource=resource,
            endpoint_template=f"/{resource}",
            status_code=200,
            duration_ms=1,
            payload={"origin_id": 2},
        )
        for resource in ("settings", "customers", "lawsuits")
    ]

    status, _ = classify_linkage(observations)

    assert status is LinkageStatus.INCONCLUSIVO


def test_reports_never_render_payload_values() -> None:
    secret_value = "SYNTHETIC_PERSON_NEVER_RENDER"
    observation = sanitize_payload(
        resource="customers",
        endpoint_template="/customers",
        status_code=200,
        duration_ms=4,
        payload={"data": [{"name": secret_value, "portfolio_id": 1}]},
    )
    now = datetime.now(UTC)
    result = AuditRunResult(
        started_at=now,
        finished_at=now,
        observations=(observation,),
        linkage_status=LinkageStatus.INCONCLUSIVO,
        linkage_evidence=("Evidência sintética sem valor de campo.",),
    )

    rendered = render_api_audit(result) + render_linkage_report(result)

    assert secret_value not in rendered
    assert "data[].name" in rendered
    assert "data[].portfolio_id" in rendered

"""Portal routes run only against synthetic partners and report artifacts."""

import asyncio
import io
import json
import re
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from partner_reports.config import AppEnvironment, Settings
from partner_reports.main import create_app
from partner_reports.pdf_imports.storage import LocalPrivatePdfStorage, PdfStorageUnavailable
from partner_reports.persistence.models import (
    AppUser,
    AuditEvent,
    Partner,
    PdfImportBatch,
    PdfImportEvent,
    PdfSourceDocument,
    PortalCredential,
    ReportGenerationRequest,
    ReportVersion,
    Role,
    UserRole,
)
from partner_reports.web.artifacts import ArtifactUnavailable, SyntheticArtifactStore
from partner_reports.web.security import COOKIE_NAME, hash_password
from partner_reports.web.user_cli import main as user_cli_main

pytestmark = pytest.mark.database


@pytest.fixture
def portal(db_session: Session, tmp_path: Path):
    viewer_role = db_session.scalar(select(Role).where(Role.key == "portal_viewer"))
    admin_role = db_session.scalar(select(Role).where(Role.key == "portal_admin"))
    if viewer_role is None:
        viewer_role = Role(key="portal_viewer")
        db_session.add(viewer_role)
    if admin_role is None:
        admin_role = Role(key="portal_admin")
        db_session.add(admin_role)
    db_session.flush()
    viewer = AppUser(external_subject=f"local:synthetic-viewer-{uuid.uuid4().hex}", status="active")
    admin = AppUser(external_subject=f"local:synthetic-admin-{uuid.uuid4().hex}", status="active")
    db_session.add_all([viewer, admin])
    db_session.flush()
    db_session.add_all(
        [
            PortalCredential(
                user_id=viewer.id,
                login_name="synthetic-viewer",
                password_hash=hash_password("synthetic-long-password-viewer"),
            ),
            PortalCredential(
                user_id=admin.id,
                login_name="synthetic-admin",
                password_hash=hash_password("synthetic-long-password-admin"),
            ),
            UserRole(user_id=viewer.id, role_id=viewer_role.id),
            UserRole(user_id=admin.id, role_id=admin_role.id),
        ]
    )
    partner_a = Partner(external_id="SYNTHETIC-PORTAL-A", name="Alfa Sintético")
    partner_b = Partner(external_id="SYNTHETIC-PORTAL-B", name="Beta Sintético")
    db_session.add_all([partner_a, partner_b])
    db_session.flush()
    version = ReportVersion(
        partner_id=partner_a.id,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 16),
        version=1,
        status="validated",
        generated_at=datetime(2026, 9, 16, 12, 1, tzinfo=UTC),
        storage_object_key="synthetic/one",
    )
    db_session.add(version)
    db_session.flush()
    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://synthetic:synthetic@db/synthetic",
        _env_file=None,
    )
    app = create_app(settings)
    app.state.session_factory = sessionmaker(
        bind=db_session.get_bind(),
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    app.state.artifact_store = SyntheticArtifactStore(Path("output"), settings.app_env)
    app.state.pdf_import_storage = LocalPrivatePdfStorage(
        tmp_path / "pdf-storage", settings.app_env
    )
    with TestClient(app, base_url="https://testserver") as client:
        yield client, partner_a, partner_b, version


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf" value="([0-9a-f]+)"', html)
    assert match
    return match.group(1)


def _login(
    client: TestClient,
    login: str = "synthetic-viewer",
    password: str = "synthetic-long-password-viewer",
):
    login_page = client.get("/portal/login")
    assert login_page.status_code == 200
    assert COOKIE_NAME in client.cookies
    return client.post(
        "/portal/login",
        data={"csrf": _csrf(login_page.text), "login": login, "password": password},
        follow_redirects=False,
    )


def _synthetic_source_pdf() -> bytes:
    stream = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595.28, height=841.89)
    writer.write(stream)
    return stream.getvalue()


def test_login_catalog_search_and_detail(portal) -> None:
    client, partner_a, partner_b, _ = portal
    assert client.get("/portal/partners").status_code == 401
    response = _login(client)
    assert response.status_code == 303
    assert "Secure" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    result = client.get("/portal/partners?q=Alfa&status=atualizado")
    assert result.status_code == 200
    assert partner_a.name in result.text
    assert partner_b.name not in result.text
    detail = client.get(f"/portal/partners/{partner_a.id}")
    assert detail.status_code == 200
    assert "Histórico de versões" in detail.text
    assert "v1" in detail.text
    assert "Regenerar apenas este parceiro" not in detail.text


def test_artifact_is_scoped_to_partner_and_local_synthetic(portal) -> None:
    client, partner_a, partner_b, version = portal
    _login(client)
    html = client.get(f"/portal/partners/{partner_a.id}/versions/{version.id}/html")
    pdf = client.get(f"/portal/partners/{partner_a.id}/versions/{version.id}/pdf")
    assert html.status_code == 200
    assert "SYNTHETIC-ONE" in html.text
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    assert "attachment" in pdf.headers["content-disposition"]
    assert (
        client.get(f"/portal/partners/{partner_b.id}/versions/{version.id}/pdf").status_code == 404
    )
    assert (
        client.get(f"/portal/partners/{partner_a.id}/versions/{uuid.uuid4()}/html").status_code
        == 404
    )
    assert (
        client.get(f"/portal/partners/{partner_a.id}/versions/{version.id}/txt").status_code == 404
    )
    with pytest.raises(ArtifactUnavailable):
        SyntheticArtifactStore(Path("output"), AppEnvironment.PRODUCTION).read(
            "synthetic/one", "pdf"
        )


def test_missing_report_queues_once_and_regeneration_needs_admin(
    portal, db_session: Session
) -> None:
    client, _, partner_b, _ = portal
    _login(client)
    detail = client.get(f"/portal/partners/{partner_b.id}")
    assert "Sem versões" in detail.text
    assert (
        client.post(
            f"/portal/partners/{partner_b.id}/regenerate", data={"csrf": _csrf(detail.text)}
        ).status_code
        == 403
    )
    for _ in range(2):
        response = client.post(
            f"/portal/partners/{partner_b.id}/open",
            data={"csrf": _csrf(detail.text)},
            follow_redirects=False,
        )
        assert response.status_code == 303
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(ReportGenerationRequest)
            .where(ReportGenerationRequest.partner_id == partner_b.id)
        )
        == 1
    )
    assert "gerando" in client.get(f"/portal/partners/{partner_b.id}").text


def test_csrf_logout_and_login_rate_limit(portal) -> None:
    client, partner_a, _, _ = portal
    login_page = client.get("/portal/login")
    assert (
        client.post(
            "/portal/login", data={"csrf": "bad", "login": "synthetic-viewer", "password": "x"}
        ).status_code
        == 403
    )
    token = _csrf(login_page.text)
    for _ in range(5):
        assert (
            client.post(
                "/portal/login",
                data={"csrf": token, "login": "synthetic-viewer", "password": "wrong"},
            ).status_code
            == 200
        )
    assert (
        client.post(
            "/portal/login", data={"csrf": token, "login": "synthetic-viewer", "password": "wrong"}
        ).status_code
        == 429
    )
    # A different test client address would be needed to log in; this one remains throttled.
    assert client.get(f"/portal/partners/{partner_a.id}").status_code == 401


def test_admin_regenerate_and_logout(portal, db_session: Session) -> None:
    client, partner_a, _, _ = portal
    assert _login(client, "synthetic-admin", "synthetic-long-password-admin").status_code == 303
    detail = client.get(f"/portal/partners/{partner_a.id}")
    assert "Regenerar apenas este parceiro" in detail.text
    csrf = _csrf(detail.text)
    assert (
        client.post(f"/portal/partners/{partner_a.id}/regenerate", data={"csrf": "bad"}).status_code
        == 403
    )
    assert (
        client.post(
            f"/portal/partners/{partner_a.id}/regenerate",
            data={"csrf": csrf},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(ReportGenerationRequest)
            .where(ReportGenerationRequest.partner_id == partner_a.id)
        )
        == 1
    )
    assert (
        client.post("/portal/logout", data={"csrf": csrf}, follow_redirects=False).status_code
        == 303
    )
    assert client.get("/portal/partners").status_code == 401


def test_admin_can_upload_private_pdf_and_duplicate_is_idempotent(
    portal, db_session: Session
) -> None:
    client, partner, _, _ = portal
    assert _login(client, "synthetic-admin", "synthetic-long-password-admin").status_code == 303
    page = client.get("/portal/imports/new")
    assert page.status_code == 200
    content = _synthetic_source_pdf()
    payload = {
        "csrf": _csrf(page.text),
        "partner_id": str(partner.id),
        "period_start": "2026-09-01",
        "period_end": "2026-09-30",
    }
    received = client.post(
        "/portal/imports/new",
        data=payload,
        files={"source_pdf": ("synthetic.pdf", content, "application/pdf")},
        follow_redirects=False,
    )
    assert received.status_code == 303
    batch = db_session.scalar(select(PdfImportBatch))
    assert batch is not None and batch.state == "quarantined"
    source = db_session.scalar(select(PdfSourceDocument))
    assert source is not None
    assert source.page_count == 1
    assert "synthetic.pdf" not in " ".join(str(value) for value in source.__dict__.values())
    assert db_session.scalar(select(func.count()).select_from(PdfImportEvent)) == 2
    detail = client.get(received.headers["location"])
    assert detail.status_code == 200
    assert "ainda não foi interpretado" in detail.text

    duplicate = client.post(
        "/portal/imports/new",
        data=payload,
        files={"source_pdf": ("another-name.pdf", content, "application/pdf")},
    )
    assert duplicate.status_code == 409
    assert db_session.scalar(select(func.count()).select_from(PdfImportBatch)) == 1
    actions = set(db_session.scalars(select(AuditEvent.action)).all())
    assert {"pdf_upload_succeeded", "pdf_upload_duplicate"} <= actions


def test_pdf_upload_requires_admin_and_csrf(portal) -> None:
    client, partner, _, _ = portal
    assert _login(client).status_code == 303
    assert client.get("/portal/imports/new").status_code == 403

    client.post("/portal/logout", data={"csrf": _csrf(client.get("/portal/partners").text)})
    assert _login(client, "synthetic-admin", "synthetic-long-password-admin").status_code == 303
    content = _synthetic_source_pdf()
    denied = client.post(
        "/portal/imports/new",
        data={
            "csrf": "bad",
            "partner_id": str(partner.id),
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
        files={"source_pdf": ("synthetic.pdf", content, "application/pdf")},
    )
    assert denied.status_code == 403


def test_pdf_upload_rejects_fake_and_handles_storage_failure(
    portal, db_session: Session, monkeypatch
) -> None:
    client, partner, _, _ = portal
    assert _login(client, "synthetic-admin", "synthetic-long-password-admin").status_code == 303
    page = client.get("/portal/imports/new")
    payload = {
        "csrf": _csrf(page.text),
        "partner_id": str(partner.id),
        "period_start": "2026-09-01",
        "period_end": "2026-09-30",
    }
    fake = client.post(
        "/portal/imports/new",
        data=payload,
        files={"source_pdf": ("synthetic.pdf", b"not-a-pdf", "application/pdf")},
    )
    assert fake.status_code == 400

    def unavailable(_key, _content):
        raise PdfStorageUnavailable("synthetic private failure")

    monkeypatch.setattr(client.app.state.pdf_import_storage, "put", unavailable)
    failed = client.post(
        "/portal/imports/new",
        data=payload,
        files={"source_pdf": ("synthetic.pdf", _synthetic_source_pdf(), "application/pdf")},
    )
    assert failed.status_code == 503
    assert "synthetic private failure" not in failed.text
    assert db_session.scalar(select(func.count()).select_from(PdfImportBatch)) == 0
    reasons = set(db_session.scalars(select(AuditEvent.reason_code)).all())
    assert {"FILE_NOT_PDF", "STORAGE_UNAVAILABLE"} <= reasons


def test_pagination_and_status_filter(portal, db_session: Session) -> None:
    client, _, _, _ = portal
    db_session.add_all(
        [
            Partner(external_id=f"SYNTHETIC-PAGE-{i:02d}", name=f"Carteira Sintética {i:02d}")
            for i in range(13)
        ]
    )
    db_session.flush()
    _login(client)
    page_1 = client.get("/portal/partners?status=sem+relat%C3%B3rio")
    assert page_1.status_code == 200
    assert "Página 1 de 2" in page_1.text
    page_2 = client.get("/portal/partners?status=sem+relat%C3%B3rio&page=2")
    assert "Página 2 de 2" in page_2.text
    assert "Carteira Sintética 12" in page_2.text


def test_security_audit_and_headers(portal, db_session: Session, caplog) -> None:
    client, partner_a, _, version = portal
    assert _login(client, "synthetic-admin", "synthetic-long-password-admin").status_code == 303
    listing = client.get("/portal/partners")
    detail = client.get(f"/portal/partners/{partner_a.id}")
    html = client.get(f"/portal/partners/{partner_a.id}/versions/{version.id}/html")
    pdf = client.get(f"/portal/partners/{partner_a.id}/versions/{version.id}/pdf")
    requested = client.post(
        f"/portal/partners/{partner_a.id}/regenerate",
        data={"csrf": _csrf(detail.text)},
        follow_redirects=False,
    )
    assert all(item.status_code in (200, 303) for item in (listing, detail, html, pdf, requested))
    assert (
        client.post(
            "/portal/logout", data={"csrf": _csrf(detail.text)}, follow_redirects=False
        ).status_code
        == 303
    )
    for response in (listing, html, pdf):
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["cross-origin-resource-policy"] == "same-origin"
    actions = set(db_session.scalars(select(AuditEvent.action)).all())
    assert {
        "login_succeeded",
        "catalog_view",
        "partner_view",
        "report_view",
        "report_download",
        "generation_requested",
        "logout",
    } <= actions
    for event in db_session.scalars(select(AuditEvent)).all():
        assert event.changed_fields == []
        assert event.reason_code in (None, "invalid_credentials", "rate_limited", "access_denied")
    for record in caplog.records:
        if record.name == "partner_reports.security":
            assert set(json.loads(record.message)) == {
                "event",
                "correlation_id",
                "entity_type",
            }
            assert "synthetic-long-password" not in record.message


def test_denied_download_traversal_and_error_do_not_leak(portal, db_session, monkeypatch, caplog):
    client, partner_a, partner_b, version = portal
    path = f"/portal/partners/{partner_a.id}/versions/{version.id}/pdf"
    denied = client.get(path)
    assert denied.status_code == 401 and not denied.content.startswith(b"%PDF")
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "artifact_denied")
        )
        >= 1
    )
    _login(client)
    assert (
        client.get(f"/portal/partners/{partner_b.id}/versions/{version.id}/pdf").status_code == 404
    )
    store = SyntheticArtifactStore(Path("output"), AppEnvironment.TEST)
    for key in (
        "synthetic/generated/../../.env",
        "synthetic/../.env",
        "synthetic/generated/a/../b",
    ):
        with pytest.raises(ArtifactUnavailable):
            store.read(key, "pdf")
    forbidden = "SYNTHETIC_SECRET_NEVER_DISCLOSE"

    def broken_read(_key, _kind):
        raise ArtifactUnavailable(forbidden)

    monkeypatch.setattr(client.app.state.artifact_store, "read", broken_read)
    unavailable = client.get(path)
    assert unavailable.status_code == 404
    assert forbidden not in unavailable.text
    assert forbidden not in caplog.text
    assert forbidden not in " ".join(
        str(event.__dict__) for event in db_session.scalars(select(AuditEvent)).all()
    )


def test_admin_can_disable_account_and_revoke_live_session(portal, db_session, monkeypatch):
    client, partner_a, _, _ = portal
    assert _login(client).status_code == 303
    assert client.get(f"/portal/partners/{partner_a.id}").status_code == 200
    sessions = sessionmaker(
        bind=db_session.get_bind(), expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    monkeypatch.setattr("partner_reports.web.user_cli.get_session_factory", lambda: sessions)
    monkeypatch.setattr(
        "partner_reports.web.user_cli.getpass.getpass",
        lambda _prompt: "synthetic-long-password-admin",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "portal-user",
            "disable",
            "--login",
            "synthetic-viewer",
            "--actor-login",
            "synthetic-admin",
        ],
    )
    user_cli_main()
    assert client.get(f"/portal/partners/{partner_a.id}").status_code == 401
    assert "account_disabled" in set(db_session.scalars(select(AuditEvent.action)).all())


@pytest.mark.browser
def test_portal_visual_layout_and_palette(portal) -> None:
    from playwright.async_api import async_playwright

    client, partner_a, _, _ = portal
    login_html = client.get("/portal/login").text
    _login(client)
    list_html = client.get("/portal/partners").text
    detail_html = client.get(f"/portal/partners/{partner_a.id}").text
    css = client.get("/portal/assets.css").text
    assert "#F4AA27" in css
    assert "#FFC14D" in css
    assert "#0A0A0A" in css
    assert "#EDEDED" in css
    pages = {
        "login": login_html,
        "portal": list_html,
        "detail": detail_html,
    }

    async def check() -> None:
        output = Path("output/preview")
        output.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                for view, source in pages.items():
                    html = source.replace(
                        '<link rel="stylesheet" href="/portal/assets.css">',
                        f"<style>{css}</style>",
                    )
                    for width, label in ((1280, "desktop"), (375, "mobile")):
                        page = await browser.new_page(
                            viewport={"width": width, "height": 950}, device_scale_factor=1
                        )
                        await page.set_content(html)
                        size = await page.evaluate(
                            "({scroll:document.documentElement.scrollWidth,inner:innerWidth})"
                        )
                        assert size["scroll"] <= size["inner"]
                        background = await page.locator("body").evaluate(
                            "element => getComputedStyle(element).backgroundColor"
                        )
                        assert background == "rgb(10, 10, 10)"
                        await page.locator(".button-primary").hover()
                        await page.wait_for_function(
                            "getComputedStyle(document.querySelector('.button-primary'))"
                            ".backgroundColor === 'rgb(255, 193, 77)'"
                        )
                        hover = await page.locator(".button-primary").evaluate(
                            "element => getComputedStyle(element).backgroundColor"
                        )
                        assert hover == "rgb(255, 193, 77)"
                        await page.screenshot(
                            path=str(output / f"{view}_{label}.png"), full_page=True
                        )
                        await page.close()
            finally:
                await browser.close()

    asyncio.run(check())

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
from partner_reports.web.artifacts import (
    ArtifactUnavailable,
    SyntheticArtifactStore,
    build_artifact_store,
)
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
    root = client.get("/", follow_redirects=False)
    assert root.status_code == 303
    assert root.headers["location"] == "/portal/login"
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
    signed_in = client.get("/", follow_redirects=True)
    assert signed_in.status_code == 200
    assert str(signed_in.url).endswith("/portal/partners")


def test_private_pilot_scope_uses_database_flag(portal, db_session: Session) -> None:
    client, synthetic_partner, _, _ = portal
    allowed = Partner(external_id="PILOT-001", name="Parceiro piloto permitido", pilot_enabled=True)
    blocked = Partner(external_id="PILOT-002", name="Parceiro piloto bloqueado")
    synthetic_partner.pilot_enabled = True
    db_session.add_all([allowed, blocked])
    db_session.flush()
    client.app.state.settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://synthetic:synthetic@db/synthetic",
        pdf_data_scope="private_pilot",
        _env_file=None,
    )

    assert _login(client, "synthetic-admin", "synthetic-long-password-admin").status_code == 303
    catalog = client.get("/portal/partners")
    assert catalog.status_code == 200
    assert allowed.name in catalog.text
    assert blocked.name not in catalog.text
    assert synthetic_partner.name not in catalog.text
    assert client.get(f"/portal/partners/{allowed.id}").status_code == 200
    assert client.get(f"/portal/partners/{blocked.id}").status_code == 404
    assert client.get(f"/portal/partners/{synthetic_partner.id}").status_code == 404

    upload = client.get("/portal/imports/new")
    assert upload.status_code == 200
    assert allowed.name in upload.text
    assert blocked.name not in upload.text
    assert synthetic_partner.name not in upload.text


def _pilot_settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="postgresql+psycopg://synthetic:synthetic@db/synthetic",
        pdf_data_scope="private_pilot",
        _env_file=None,
    )


def _partner_audit(db_session: Session, action: str, partner_id: uuid.UUID) -> int:
    return db_session.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.action == action,
            AuditEvent.entity_type == "partner",
            AuditEvent.entity_id == partner_id,
        )
    )


def test_admin_registers_and_releases_partner_gradually(portal, db_session: Session) -> None:
    client, _, _, _ = portal
    client.app.state.settings = _pilot_settings()
    assert _login(client, "synthetic-admin", "synthetic-long-password-admin").status_code == 303
    page = client.get("/portal/admin/partners")
    assert page.status_code == 200
    assert "Nenhum parceiro cadastrado" in page.text

    created = client.post(
        "/portal/admin/partners",
        data={"csrf": _csrf(page.text), "name": "  Parceiro   Sintético  Gradual "},
        follow_redirects=False,
    )
    assert created.status_code == 303
    partner = db_session.scalar(select(Partner).where(Partner.name == "Parceiro Sintético Gradual"))
    assert partner is not None
    assert re.fullmatch(r"PRT-[0-9A-F]{10}", partner.external_id)
    assert partner.status == "active"
    assert partner.pilot_enabled is False
    assert _partner_audit(db_session, "partner_created", partner.id) == 1

    # Registered but not released: invisible to the catalog, detail and upload flows.
    assert partner.name not in client.get("/portal/partners").text
    assert client.get(f"/portal/partners/{partner.id}").status_code == 404
    assert partner.name not in client.get("/portal/imports/new").text

    csrf = _csrf(client.get("/portal/admin/partners").text)
    unconfirmed = client.post(
        f"/portal/admin/partners/{partner.id}/pilot/enable",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert unconfirmed.status_code == 400
    enabled = client.post(
        f"/portal/admin/partners/{partner.id}/pilot/enable",
        data={"csrf": csrf, "confirm": "yes"},
        follow_redirects=False,
    )
    assert enabled.status_code == 303
    db_session.refresh(partner)
    assert partner.pilot_enabled is True
    assert _partner_audit(db_session, "partner_pilot_enabled", partner.id) == 1
    assert partner.name in client.get("/portal/partners").text
    assert client.get(f"/portal/partners/{partner.id}").status_code == 200
    assert partner.name in client.get("/portal/imports/new").text

    repeated = client.post(
        f"/portal/admin/partners/{partner.id}/pilot/enable",
        data={"csrf": csrf, "confirm": "yes"},
        follow_redirects=False,
    )
    assert repeated.status_code == 303
    assert _partner_audit(db_session, "partner_pilot_enabled", partner.id) == 1

    disabled = client.post(
        f"/portal/admin/partners/{partner.id}/pilot/disable",
        data={"csrf": csrf, "confirm": "yes"},
        follow_redirects=False,
    )
    assert disabled.status_code == 303
    db_session.refresh(partner)
    assert partner.pilot_enabled is False
    assert _partner_audit(db_session, "partner_pilot_disabled", partner.id) == 1
    assert client.get(f"/portal/partners/{partner.id}").status_code == 404


def test_partner_admin_rejects_invalid_requests(portal, db_session: Session) -> None:
    client, synthetic_partner, _, _ = portal
    # Synthetic runtimes never register real partners.
    assert _login(client, "synthetic-admin", "synthetic-long-password-admin").status_code == 303
    assert client.get("/portal/admin/partners").status_code == 404
    assert "Gerenciar parceiros" not in client.get("/portal/partners").text

    client.app.state.settings = _pilot_settings()
    page = client.get("/portal/admin/partners")
    csrf = _csrf(page.text)
    before = db_session.scalar(select(func.count()).select_from(Partner))
    for name in ("", "x", "a" * 121, "Nome\x00oculto"):
        rejected = client.post("/portal/admin/partners", data={"csrf": csrf, "name": name})
        assert rejected.status_code == 400
    assert (
        client.post(
            "/portal/admin/partners", data={"csrf": "0" * 32, "name": "Parceiro válido"}
        ).status_code
        == 403
    )
    assert db_session.scalar(select(func.count()).select_from(Partner)) == before

    # Synthetic partners cannot be promoted into the real pilot scope.
    promoted = client.post(
        f"/portal/admin/partners/{synthetic_partner.id}/pilot/enable",
        data={"csrf": csrf, "confirm": "yes"},
    )
    assert promoted.status_code == 404
    assert (
        client.post(
            f"/portal/admin/partners/{synthetic_partner.id}/pilot/publish",
            data={"csrf": csrf, "confirm": "yes"},
        ).status_code
        == 400
    )

    client.post("/portal/logout", data={"csrf": csrf})
    assert _login(client).status_code == 303
    assert client.get("/portal/admin/partners").status_code == 403


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


def test_pdf_batch_report_requires_admin_and_checks_artifact_integrity(
    portal, db_session: Session
) -> None:
    import hashlib

    client, partner, _, version = portal
    source = PdfSourceDocument(
        source_sha256=uuid.uuid4().hex * 2,
        storage_object_key=f"pdf-source/{uuid.uuid4().hex}.pdf",
        byte_size=1000,
        page_count=1,
        media_type="application/pdf",
    )
    db_session.add(source)
    db_session.flush()
    batch = PdfImportBatch(
        source_document_id=source.id,
        partner_id=partner.id,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 16),
        parser_version="advbox-manifest-1",
        parsed_item_count=1,
        state="approved",
    )
    db_session.add(batch)
    db_session.flush()
    version.pdf_batch_id = batch.id
    store = client.app.state.artifact_store
    version.content_sha256 = hashlib.sha256(
        store.read("synthetic/one", "html") + store.read("synthetic/one", "pdf")
    ).hexdigest()
    db_session.flush()
    assert _login(client).status_code == 303
    detail = client.get(f"/portal/partners/{partner.id}")
    assert f"versions/{version.id}/pdf" in detail.text
    assert source.storage_object_key not in detail.text
    assert (
        client.post(
            f"/portal/imports/{batch.id}/generate",
            data={"csrf": _csrf(detail.text), "confirm": "yes"},
        ).status_code
        == 403
    )
    assert client.get(f"/portal/partners/{partner.id}/versions/{version.id}/pdf").status_code == 200
    version.content_sha256 = "0" * 64
    db_session.flush()
    assert client.get(f"/portal/partners/{partner.id}/versions/{version.id}/pdf").status_code == 404
    client.post("/portal/logout", data={"csrf": _csrf(detail.text)})
    assert _login(client, "synthetic-admin", "synthetic-long-password-admin").status_code == 303
    batch_detail = client.get(f"/portal/imports/{batch.id}")
    assert "Relatório pronto" in batch_detail.text
    assert (
        client.post(
            f"/portal/imports/{batch.id}/generate",
            data={"csrf": "bad", "confirm": "yes"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/portal/imports/{batch.id}/generate",
            data={"csrf": _csrf(batch_detail.text), "confirm": "yes"},
        ).status_code
        == 409
    )


def test_admin_can_restore_prior_validated_version(portal, db_session: Session) -> None:
    client, partner, _, first = portal
    second = ReportVersion(
        partner_id=partner.id,
        period_start=first.period_start,
        period_end=first.period_end,
        version=2,
        status="validated",
        generated_at=datetime(2026, 9, 16, 13, tzinfo=UTC),
        storage_object_key="synthetic/one",
    )
    db_session.add(second)
    db_session.flush()
    assert _login(client, "synthetic-admin", "synthetic-long-password-admin").status_code == 303
    detail = client.get(f"/portal/partners/{partner.id}")
    assert "Restaurar v1" in detail.text
    url = f"/portal/partners/{partner.id}/versions/{first.id}/restore"
    assert client.post(url, data={"csrf": "bad", "confirm": "yes"}).status_code == 403
    assert client.post(url, data={"csrf": _csrf(detail.text)}).status_code == 400
    restored = client.post(
        url, data={"csrf": _csrf(detail.text), "confirm": "yes"}, follow_redirects=False
    )
    assert restored.status_code == 303
    db_session.refresh(second)
    assert second.status == "superseded"
    detail = client.get(f"/portal/partners/{partner.id}")
    assert "Restaurar v2" in detail.text
    assert f"versions/{first.id}/html" in detail.text
    assert client.get(f"/portal/partners/{partner.id}/versions/{second.id}/pdf").status_code == 404
    assert (
        client.post(
            f"/portal/partners/{partner.id}/versions/{second.id}/restore",
            data={"csrf": _csrf(detail.text), "confirm": "yes"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert client.get(f"/portal/partners/{partner.id}/versions/{second.id}/pdf").status_code == 200


def test_admin_can_restore_integral_private_pilot_version(
    portal, db_session: Session, tmp_path: Path
) -> None:
    client, _, _, _ = portal
    partner = Partner(
        external_id="PILOT-RESTORE-001", name="Parceiro piloto de teste", pilot_enabled=True
    )
    source = PdfSourceDocument(
        source_sha256="a" * 64,
        storage_object_key="private/source/opaque-test.pdf",
        byte_size=1000,
        page_count=1,
        media_type="application/pdf",
    )
    db_session.add_all([partner, source])
    db_session.flush()
    batch = PdfImportBatch(
        source_document_id=source.id,
        partner_id=partner.id,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        parser_version="private-pilot-test-1",
        parsed_item_count=1,
        state="approved",
    )
    db_session.add(batch)
    db_session.flush()

    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://synthetic:synthetic@db/synthetic",
        pdf_data_scope="private_pilot",
        _env_file=None,
    )
    client.app.state.settings = settings
    store = build_artifact_store(
        tmp_path / "private-reports", settings.app_env, settings.pdf_data_scope
    )
    client.app.state.artifact_store = store
    first_key, first_digest = store.write_generated(
        b"<!doctype html><title>Private pilot v1</title>", b"%PDF-1.4\nprivate-pilot-v1"
    )
    second_key, second_digest = store.write_generated(
        b"<!doctype html><title>Private pilot v2</title>", b"%PDF-1.4\nprivate-pilot-v2"
    )
    first = ReportVersion(
        partner_id=partner.id,
        pdf_batch_id=batch.id,
        period_start=batch.period_start,
        period_end=batch.period_end,
        version=1,
        status="validated",
        generated_at=datetime(2026, 9, 30, 12, tzinfo=UTC),
        storage_object_key=first_key,
        content_sha256=first_digest,
    )
    second = ReportVersion(
        partner_id=partner.id,
        pdf_batch_id=batch.id,
        period_start=batch.period_start,
        period_end=batch.period_end,
        version=2,
        status="validated",
        generated_at=datetime(2026, 9, 30, 13, tzinfo=UTC),
        storage_object_key=second_key,
        content_sha256=second_digest,
    )
    db_session.add_all([first, second])
    db_session.flush()

    assert _login(client, "synthetic-admin", "synthetic-long-password-admin").status_code == 303
    detail = client.get(f"/portal/partners/{partner.id}")
    restored = client.post(
        f"/portal/partners/{partner.id}/versions/{first.id}/restore",
        data={"csrf": _csrf(detail.text), "confirm": "yes"},
        follow_redirects=False,
    )
    assert restored.status_code == 303
    db_session.refresh(first)
    db_session.refresh(second)
    assert first.status == "validated"
    assert second.status == "superseded"
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action == "report_version_restored",
                AuditEvent.entity_id == first.id,
            )
        )
        == 1
    )

    second.content_sha256 = "0" * 64
    db_session.flush()
    detail = client.get(f"/portal/partners/{partner.id}")
    rejected = client.post(
        f"/portal/partners/{partner.id}/versions/{second.id}/restore",
        data={"csrf": _csrf(detail.text), "confirm": "yes"},
        follow_redirects=False,
    )
    assert rejected.status_code == 404
    db_session.refresh(second)
    assert second.status == "superseded"


@pytest.mark.browser
def test_pdf6_portal_layout_with_long_synthetic_name(portal, db_session: Session) -> None:
    from playwright.async_api import async_playwright

    client, partner, _, first = portal
    partner.name = "Parceiro sintético " + "NomeComprido" * 12
    source = PdfSourceDocument(
        source_sha256=uuid.uuid4().hex * 2,
        storage_object_key=f"pdf-source/{uuid.uuid4().hex}.pdf",
        byte_size=1000,
        page_count=1,
        media_type="application/pdf",
    )
    db_session.add(source)
    db_session.flush()
    batch = PdfImportBatch(
        source_document_id=source.id,
        partner_id=partner.id,
        period_start=first.period_start,
        period_end=first.period_end,
        parser_version="advbox-manifest-1",
        parsed_item_count=1,
        state="approved",
    )
    db_session.add(batch)
    db_session.flush()
    first.pdf_batch_id = batch.id
    db_session.add(
        ReportVersion(
            partner_id=partner.id,
            period_start=first.period_start,
            period_end=first.period_end,
            version=2,
            status="validated",
            generated_at=datetime(2026, 9, 16, 13, tzinfo=UTC),
            storage_object_key="synthetic/one",
            pdf_batch_id=batch.id,
        )
    )
    db_session.flush()
    _login(client, "synthetic-admin", "synthetic-long-password-admin")
    pages = {
        "partner": client.get(f"/portal/partners/{partner.id}").text,
        "batch": client.get(f"/portal/imports/{batch.id}").text,
    }
    assert "Restaurar v1" in pages["partner"]
    assert "Relatório pronto" in pages["batch"]
    assert source.storage_object_key not in " ".join(pages.values())
    css = client.get("/portal/assets.css").text

    async def check() -> None:
        output = Path("output/preview")
        output.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                for name, source_html in pages.items():
                    html = source_html.replace(
                        '<link rel="stylesheet" href="/portal/assets.css">',
                        f"<style>{css}</style>",
                    )
                    for width, size in ((1280, "desktop"), (375, "mobile")):
                        page = await browser.new_page(viewport={"width": width, "height": 950})
                        await page.set_content(html)
                        overflow = await page.evaluate(
                            """() => ({
                                width: document.documentElement.scrollWidth,
                                viewport: innerWidth,
                                offenders: [...document.querySelectorAll('*')]
                                  .filter(el => el.getBoundingClientRect().right > innerWidth + 1)
                                  .slice(0, 5)
                                  .map(el => [el.tagName, el.className])
                            })"""
                        )
                        assert overflow["width"] <= overflow["viewport"], (name, size, overflow)
                        await page.screenshot(
                            path=str(output / f"pdf6_{name}_{size}.png"), full_page=True
                        )
                        await page.close()
            finally:
                await browser.close()

    asyncio.run(check())


def test_partner_page_offers_only_the_upload_flow(portal) -> None:
    client, _, partner_b, _ = portal
    _login(client)
    detail = client.get(f"/portal/partners/{partner_b.id}")
    assert "Nenhum relatório ainda" in detail.text
    assert "/portal/imports/new" not in detail.text
    for retired in ("open", "regenerate"):
        response = client.post(
            f"/portal/partners/{partner_b.id}/{retired}", data={"csrf": _csrf(detail.text)}
        )
        assert response.status_code in (404, 405)


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


def test_admin_partner_page_links_new_report_and_logout(portal) -> None:
    client, partner_a, _, version = portal
    assert _login(client, "synthetic-admin", "synthetic-long-password-admin").status_code == 303
    detail = client.get(f"/portal/partners/{partner_a.id}")
    assert f"/portal/imports/new?parceiro={partner_a.id}" in detail.text
    assert f"versions/{version.id}/html" in detail.text
    assert "Regenerar" not in detail.text
    csrf = _csrf(detail.text)
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
    batch = db_session.scalar(select(PdfImportBatch).where(PdfImportBatch.partner_id == partner.id))
    assert batch is not None and batch.state == "quarantined"
    source = db_session.get(PdfSourceDocument, batch.source_document_id)
    assert source is not None
    assert source.page_count == 1
    assert "synthetic.pdf" not in " ".join(str(value) for value in source.__dict__.values())
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PdfImportEvent)
            .where(PdfImportEvent.batch_id == batch.id)
        )
        == 2
    )
    detail = client.get(received.headers["location"])
    assert detail.status_code == 200
    assert "Conferindo o PDF no Advbox" in detail.text
    assert 'http-equiv="refresh"' in detail.text

    duplicate = client.post(
        "/portal/imports/new",
        data=payload,
        files={"source_pdf": ("another-name.pdf", content, "application/pdf")},
        follow_redirects=False,
    )
    assert duplicate.status_code == 303
    assert duplicate.headers["location"] == f"/portal/imports/{batch.id}?repetido=1"
    assert "Este PDF já tinha sido enviado" in client.get(duplicate.headers["location"]).text
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PdfImportBatch)
            .where(PdfImportBatch.partner_id == partner.id)
        )
        == 1
    )
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


def test_real_partner_is_hidden_and_rejected_by_synthetic_scope(
    portal, db_session: Session
) -> None:
    client, _, _, _ = portal
    real_partner = Partner(external_id=f"REAL-{uuid.uuid4().hex}", name="Fora do escopo")
    db_session.add(real_partner)
    db_session.flush()
    assert _login(client, "synthetic-admin", "synthetic-long-password-admin").status_code == 303
    page = client.get("/portal/imports/new")
    assert page.status_code == 200
    assert str(real_partner.id) not in page.text
    response = client.post(
        "/portal/imports/new",
        data={
            "csrf": _csrf(page.text),
            "partner_id": str(real_partner.id),
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
        files={"source_pdf": ("synthetic.pdf", _synthetic_source_pdf(), "application/pdf")},
    )
    assert response.status_code == 400
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PdfImportBatch)
            .where(PdfImportBatch.partner_id == real_partner.id)
        )
        == 0
    )
    assert client.get(f"/portal/partners/{real_partner.id}").status_code == 404


def test_pdf_review_routes_filter_csrf_and_conflict(portal, db_session: Session, caplog) -> None:
    from partner_reports.persistence.models import PdfManifestItem

    client, partner, other, _ = portal
    private_marker = "SYNTHETIC_PRIVATE_VALUE"
    source = PdfSourceDocument(
        source_sha256=uuid.uuid4().hex * 2,
        storage_object_key=f"pdf-source/{uuid.uuid4().hex}.pdf",
        byte_size=500,
        page_count=1,
        media_type="application/pdf",
    )
    db_session.add(source)
    db_session.flush()
    batch = PdfImportBatch(
        source_document_id=source.id,
        partner_id=partner.id,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        state="quarantined",
    )
    db_session.add(batch)
    db_session.flush()
    db_session.add(
        PdfManifestItem(
            batch_id=batch.id,
            source_ordinal=1,
            folder_exact=private_marker,
            source_page_start=1,
            source_page_end=1,
            quality_flags=[],
        )
    )
    db_session.flush()
    assert client.get("/portal/imports").status_code == 401
    assert client.get(f"/portal/imports/{batch.id}").status_code == 401
    _login(client)
    assert client.get("/portal/imports").status_code == 403
    assert client.get(f"/portal/imports/{batch.id}").status_code == 403
    assert (
        client.post(f"/portal/imports/{batch.id}/review/reject", data={"csrf": "bad"}).status_code
        == 403
    )
    client.post("/portal/logout", data={"csrf": _csrf(client.get("/portal/partners").text)})
    _login(client, "synthetic-admin", "synthetic-long-password-admin")
    listed = client.get(f"/portal/imports?partner_id={partner.id}&state=quarantined")
    assert listed.status_code == 200 and str(batch.id) in listed.text
    assert str(batch.id) not in client.get(f"/portal/imports?partner_id={other.id}").text
    detail = client.get(f"/portal/imports/{batch.id}")
    assert detail.status_code == 200
    assert "process_number_normalized" not in detail.text
    assert private_marker not in listed.text + detail.text
    url = f"/portal/imports/{batch.id}/review/reject"
    assert (
        client.post(url, data={"csrf": "bad", "revision": "0", "confirm": "yes"}).status_code == 403
    )
    assert client.post(url, data={"csrf": _csrf(detail.text), "revision": "0"}).status_code == 400
    accepted = client.post(
        url,
        data={"csrf": _csrf(detail.text), "revision": "0", "confirm": "yes"},
        follow_redirects=False,
    )
    db_session.refresh(batch)
    assert accepted.status_code == 303 and batch.state == "rejected"
    assert (
        client.post(
            url, data={"csrf": _csrf(detail.text), "revision": "0", "confirm": "yes"}
        ).status_code
        == 409
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "pdf_review_rejected")
        )
        == 1
    )
    assert private_marker not in caplog.text
    assert private_marker not in str(
        [vars(event) for event in db_session.scalars(select(AuditEvent)).all()]
    )


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
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(PdfImportBatch)
            .where(PdfImportBatch.partner_id == partner.id)
        )
        == 0
    )
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
    assert all(item.status_code == 200 for item in (listing, detail, html, pdf))
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


def _change_password(client: TestClient, current: str, new: str, confirm: str | None = None):
    page = client.get("/portal/account/password")
    assert page.status_code == 200
    return client.post(
        "/portal/account/password",
        data={
            "csrf": _csrf(page.text),
            "current_password": current,
            "new_password": new,
            "confirm_password": new if confirm is None else confirm,
        },
        follow_redirects=False,
    )


def test_user_changes_own_password_and_other_sessions_end(portal, db_session) -> None:
    client, partner_a, _, _ = portal
    other = TestClient(client.app, base_url="https://testserver")
    assert _login(other).status_code == 303
    assert _login(client).status_code == 303
    assert "/portal/account/password" in client.get("/portal/partners").text

    new_password = "synthetic-changed-password-viewer"
    changed = _change_password(client, "synthetic-long-password-viewer", new_password)
    assert changed.status_code == 303
    assert changed.headers["location"] == "/portal/account/password?alterada=1"
    assert "Senha alterada com sucesso" in client.get(changed.headers["location"]).text
    # The browser that changed the password keeps working; every other session ends.
    assert client.get(f"/portal/partners/{partner_a.id}").status_code == 200
    assert other.get(f"/portal/partners/{partner_a.id}").status_code == 401

    fresh = TestClient(client.app, base_url="https://testserver")
    assert _login(fresh).status_code == 200
    assert _login(fresh, password=new_password).status_code == 303
    actions = list(db_session.scalars(select(AuditEvent.action)).all())
    assert actions.count("password_changed") == 1
    assert new_password not in " ".join(
        str(event.__dict__) for event in db_session.scalars(select(AuditEvent)).all()
    )


@pytest.mark.parametrize(
    ("current", "new", "confirm", "message"),
    [
        ("wrong-current-password", "synthetic-new-password-long", None, "Senha atual incorreta"),
        ("synthetic-long-password-viewer", "curta", None, "entre 14 e 256"),
        (
            "synthetic-long-password-viewer",
            "synthetic-new-password-long",
            "synthetic-other-password",
            "não coincide",
        ),
        (
            "synthetic-long-password-viewer",
            "synthetic-long-password-viewer",
            None,
            "diferente da atual",
        ),
    ],
)
def test_password_change_rejects_invalid_input(
    portal, current: str, new: str, confirm: str | None, message: str
) -> None:
    client, _, _, _ = portal
    assert _login(client).status_code == 303
    rejected = _change_password(client, current, new, confirm)
    assert rejected.status_code == 400
    assert message in rejected.text
    # The old password still works after any rejected change.
    fresh = TestClient(client.app, base_url="https://testserver")
    assert _login(fresh).status_code == 303


def test_password_change_requires_session_csrf_and_limits_guessing(portal) -> None:
    client, _, _, _ = portal
    assert client.get("/portal/account/password").status_code == 401
    assert _login(client).status_code == 303
    forged = client.post(
        "/portal/account/password",
        data={
            "csrf": "0" * 64,
            "current_password": "synthetic-long-password-viewer",
            "new_password": "synthetic-new-password-long",
            "confirm_password": "synthetic-new-password-long",
        },
    )
    assert forged.status_code == 403
    for _ in range(5):
        assert _change_password(client, "wrong-guess-password", "synthetic-new-pw-long").status_code
    limited = _change_password(
        client, "synthetic-long-password-viewer", "synthetic-new-password-long"
    )
    assert limited.status_code == 429


def test_host_operator_lists_accounts_and_resets_forgotten_password(
    portal, db_session, monkeypatch, capsys
):
    client, partner_a, _, _ = portal
    assert _login(client, "synthetic-admin", "synthetic-long-password-admin").status_code == 303
    sessions = sessionmaker(
        bind=db_session.get_bind(), expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    monkeypatch.setattr("partner_reports.web.user_cli.get_session_factory", lambda: sessions)
    monkeypatch.setattr(sys, "argv", ["portal-user", "list"])
    user_cli_main()
    listing = capsys.readouterr().out
    assert "synthetic-admin\tactive\tportal_admin" in listing
    assert "synthetic-viewer\tactive\tportal_viewer" in listing
    assert "$argon2" not in listing

    recovered = "synthetic-recovered-password-admin"
    monkeypatch.setattr("partner_reports.web.user_cli.getpass.getpass", lambda _prompt: recovered)
    monkeypatch.setattr(
        sys, "argv", ["portal-user", "reset-password", "--login", "synthetic-admin"]
    )
    user_cli_main()
    assert recovered not in capsys.readouterr().out
    # The reset revokes live sessions and only the new password is accepted.
    assert client.get(f"/portal/partners/{partner_a.id}").status_code == 401
    fresh = TestClient(client.app, base_url="https://testserver")
    assert _login(fresh, "synthetic-admin", "synthetic-long-password-admin").status_code == 200
    assert _login(fresh, "synthetic-admin", recovered).status_code == 303
    assert "password_reset" in set(db_session.scalars(select(AuditEvent.action)).all())

    monkeypatch.setattr(
        sys, "argv", ["portal-user", "reset-password", "--login", "synthetic-missing"]
    )
    with pytest.raises(SystemExit, match="Conta não encontrada"):
        user_cli_main()


@pytest.mark.browser
def test_portal_visual_layout_and_palette(portal) -> None:
    from playwright.async_api import async_playwright

    client, partner_a, _, _ = portal
    login_html = client.get("/portal/login").text
    _login(client)
    list_html = client.get("/portal/partners").text
    detail_html = client.get(f"/portal/partners/{partner_a.id}").text
    password_html = client.get("/portal/account/password").text
    client.post("/portal/logout", data={"csrf": _csrf(list_html)})
    _login(client, "synthetic-admin", "synthetic-long-password-admin")
    upload_html = client.get("/portal/imports/new").text
    received = client.post(
        "/portal/imports/new",
        data={
            "csrf": _csrf(upload_html),
            "partner_id": str(partner_a.id),
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        },
        files={"source_pdf": ("synthetic.pdf", _synthetic_source_pdf(), "application/pdf")},
        follow_redirects=False,
    )
    batch_html = client.get(received.headers["location"]).text
    assert "Conferindo o PDF no Advbox" in batch_html
    assert "Na fila" in batch_html
    client.app.state.settings = _pilot_settings()
    admin_page = client.get("/portal/admin/partners").text
    client.post(
        "/portal/admin/partners",
        data={"csrf": _csrf(admin_page), "name": "Parceiro Sintético com Nome Bastante Longo"},
    )
    partner_admin_html = client.get("/portal/admin/partners").text
    css = client.get("/portal/assets.css").text
    assert "#F4AA27" in css
    assert "#FFC14D" in css
    assert "#0A0A0A" in css
    assert "#EDEDED" in css
    assert "appearance:none" in css
    assert "scrollbar-color:var(--gold)" in css
    assert "select option:checked" in css
    pages = {
        "login": login_html,
        "portal": list_html,
        "detail": detail_html,
        "password": password_html,
        "upload": upload_html,
        "batch": batch_html,
        "partner_admin": partner_admin_html,
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
                        if await page.locator(".button-primary").count():
                            await page.locator(".button-primary").first.hover()
                            await page.wait_for_function(
                                "getComputedStyle(document.querySelector('.button-primary'))"
                                ".backgroundColor === 'rgb(255, 193, 77)'"
                            )
                            hover = await page.locator(".button-primary").first.evaluate(
                                "element => getComputedStyle(element).backgroundColor"
                            )
                            assert hover == "rgb(255, 193, 77)"
                        box = page.locator("input[type=checkbox]").first
                        if await box.count():
                            await box.check()
                            assert await box.is_checked()
                            await page.wait_for_timeout(400)
                            assert (
                                await box.evaluate("el => getComputedStyle(el).backgroundColor")
                                == "rgb(244, 170, 39)"
                            )
                        await page.screenshot(
                            path=str(output / f"{view}_{label}.png"), full_page=True
                        )
                        await page.close()
            finally:
                await browser.close()

    asyncio.run(check())


@pytest.mark.browser
def test_pdf_review_visual_layout(portal, db_session: Session) -> None:
    from playwright.async_api import async_playwright

    from partner_reports.persistence.models import (
        PdfManifestItem,
        PdfReconciliationItem,
        PdfReconciliationRun,
    )

    client, partner, _, _ = portal
    source = PdfSourceDocument(
        source_sha256=uuid.uuid4().hex * 2,
        storage_object_key=f"pdf-source/{uuid.uuid4().hex}.pdf",
        byte_size=500,
        page_count=1,
        media_type="application/pdf",
    )
    db_session.add(source)
    db_session.flush()
    batch = PdfImportBatch(
        source_document_id=source.id,
        partner_id=partner.id,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        parser_version="synthetic-parser",
        parsed_item_count=1,
        parse_quality_count=0,
        state="needs_review",
        processing_status="succeeded",
    )
    db_session.add(batch)
    db_session.flush()
    item = PdfManifestItem(
        batch_id=batch.id,
        source_ordinal=1,
        process_number_normalized=None,
        folder_exact="SYNTHETIC-PRIVATE-VALUE",
        source_page_start=1,
        source_page_end=1,
        quality_flags=[],
    )
    run = PdfReconciliationRun(
        batch_id=batch.id,
        parser_version="synthetic-parser",
        snapshot_sha256="a" * 64,
        snapshot_total=1,
        snapshot_verified_at=datetime.now(UTC),
        result_total=1,
        matched_count=0,
        unmatched_count=1,
        ambiguous_count=0,
        duplicate_source_count=0,
        invalid_identifier_count=0,
    )
    db_session.add_all([item, run])
    db_session.flush()
    db_session.add(
        PdfReconciliationItem(
            run_id=run.id,
            manifest_item_id=item.id,
            status="unmatched",
            reason_code="NO_EXACT_MATCH",
        )
    )
    db_session.flush()
    _login(client, "synthetic-admin", "synthetic-long-password-admin")
    pages = {
        "imports": client.get("/portal/imports").text,
        "review": client.get(f"/portal/imports/{batch.id}").text,
    }
    # ADR-007: the pending item is identified so the operator knows what to fix in Advbox.
    assert "Pasta SYNTHETIC-PRIVATE-VALUE" in pages["review"]
    assert "Não encontrado no Advbox" in pages["review"]
    assert "Aprovar e gerar relatório" not in pages["review"]
    css = client.get("/portal/assets.css").text

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
                        page = await browser.new_page(viewport={"width": width, "height": 950})
                        await page.set_content(html)
                        size = await page.evaluate(
                            "({scroll:document.documentElement.scrollWidth,inner:innerWidth})"
                        )
                        assert size["scroll"] <= size["inner"]
                        await page.screenshot(
                            path=str(output / f"pdf4_{view}_{label}.png"), full_page=True
                        )
                        await page.close()
            finally:
                await browser.close()

    asyncio.run(check())


def test_upload_flow_approves_and_generates_in_one_step(portal, db_session: Session, tmp_path):
    import httpx

    from partner_reports.integrations.advbox.client import AdvboxClient
    from partner_reports.jobs.automation import process_one
    from partner_reports.pdf_imports.automation import process_one_pdf_import
    from tests.test_pdf_import_automation import (
        _api_settings,
        _create_batch,
        _sessions,
        _success_handler,
    )

    client, _, _, _ = portal
    settings = _pilot_settings()
    client.app.state.settings = settings
    storage = client.app.state.pdf_import_storage
    batch = _create_batch(db_session, storage, external_id="PILOT-FLOW")

    async def conferir() -> str:
        api = AdvboxClient(_api_settings(), transport=httpx.MockTransport(_success_handler([])))
        try:
            return await process_one_pdf_import(_sessions(db_session), settings, storage, api)
        finally:
            await api.aclose()

    _login(client, "synthetic-admin", "synthetic-long-password-admin")
    assert "Conferindo o PDF no Advbox" in client.get(f"/portal/imports/{batch.id}").text
    assert asyncio.run(conferir()) == "succeeded"
    db_session.expire_all()
    page = client.get(f"/portal/imports/{batch.id}")
    assert "Tudo certo para gerar o relatório" in page.text
    assert "Aprovar e gerar relatório" in page.text
    revision = db_session.get(PdfImportBatch, batch.id).review_revision
    url = f"/portal/imports/{batch.id}/approve"
    assert client.post(url, data={"csrf": "bad", "revision": str(revision)}).status_code == 403
    approved = client.post(
        url,
        data={"csrf": _csrf(page.text), "revision": str(revision), "confirm": "yes"},
        follow_redirects=False,
    )
    assert approved.status_code == 303
    assert approved.headers["location"] == f"/portal/imports/{batch.id}"
    db_session.expire_all()
    assert db_session.get(PdfImportBatch, batch.id).state == "approved"
    queued = db_session.scalar(
        select(ReportGenerationRequest).where(ReportGenerationRequest.pdf_batch_id == batch.id)
    )
    assert queued is not None and queued.status == "pending"
    assert "Gerando o relatório" in client.get(f"/portal/imports/{batch.id}").text
    stale = client.post(
        url,
        data={"csrf": _csrf(page.text), "revision": str(revision), "confirm": "yes"},
        follow_redirects=False,
    )
    assert stale.headers["location"].endswith("?aviso=conflito")

    async def fake_pdf(_):
        return b"%PDF-1.7\n% synthetic report"

    generated = asyncio.run(
        process_one(
            _sessions(db_session),
            AppEnvironment.TEST,
            tmp_path / "reports",
            pdf_renderer=fake_pdf,
            settings=settings,
        )
    )
    assert generated == "succeeded"
    db_session.expire_all()
    version = db_session.scalar(select(ReportVersion).where(ReportVersion.pdf_batch_id == batch.id))
    done = client.get(f"/portal/imports/{batch.id}").text
    assert "Relatório pronto" in done
    assert f"versions/{version.id}/pdf" in done
    partner_page = client.get(f"/portal/partners/{version.partner_id}").text
    assert f"versions/{version.id}/html" in partner_page
    actions = set(db_session.scalars(select(AuditEvent.action)).all())
    assert {"pdf_review_approved", "generation_requested"} <= actions


def test_failed_processing_can_be_retried_from_the_page(portal, db_session: Session) -> None:
    client, partner, _, _ = portal
    source = PdfSourceDocument(
        source_sha256=uuid.uuid4().hex * 2,
        storage_object_key=f"pdf-source/{uuid.uuid4().hex}.pdf",
        byte_size=500,
        page_count=1,
        media_type="application/pdf",
    )
    db_session.add(source)
    db_session.flush()
    batch = PdfImportBatch(
        source_document_id=source.id,
        partner_id=partner.id,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        state="quarantined",
        processing_status="failed",
        processing_attempt_count=3,
        processing_error_code="API_READ_FAILED",
    )
    db_session.add(batch)
    db_session.flush()
    _login(client, "synthetic-admin", "synthetic-long-password-admin")
    page = client.get(f"/portal/imports/{batch.id}").text
    assert "Não foi possível conferir este PDF" in page
    assert "Tentar novamente" in page
    retried = client.post(
        f"/portal/imports/{batch.id}/review/reprocess",
        data={"csrf": _csrf(page), "revision": "0", "confirm": "yes"},
        follow_redirects=False,
    )
    assert retried.status_code == 303
    db_session.refresh(batch)
    assert batch.processing_status == "pending"
    assert batch.processing_attempt_count == 0
    assert "Conferindo o PDF no Advbox" in client.get(f"/portal/imports/{batch.id}").text


def test_upload_uses_reference_month_and_refuses_future_month(portal, db_session) -> None:
    from partner_reports.web.routes.portal import _today

    client, partner, _, _ = portal
    _login(client, "synthetic-admin", "synthetic-long-password-admin")
    today = _today()
    page = client.get(f"/portal/imports/new?parceiro={partner.id}").text
    assert f'value="{today:%Y-%m}"' in page
    assert f'<option value="{partner.id}" selected>' in page
    future = date(today.year + 1, today.month, 1)
    for month, expected in ((f"{today:%Y-%m}", 303), (f"{future:%Y-%m}", 400)):
        response = client.post(
            "/portal/imports/new",
            data={"csrf": _csrf(page), "partner_id": str(partner.id), "period_month": month},
            files={
                "source_pdf": (
                    "synthetic.pdf",
                    _synthetic_source_pdf() + uuid.uuid4().bytes,
                    "application/pdf",
                )
            },
            follow_redirects=False,
        )
        assert response.status_code == expected
    batch = db_session.scalar(select(PdfImportBatch).where(PdfImportBatch.partner_id == partner.id))
    assert batch.period_start == today.replace(day=1)
    assert batch.period_end == today

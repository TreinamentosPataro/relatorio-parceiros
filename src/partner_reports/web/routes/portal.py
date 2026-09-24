"""Authenticated internal portal backed by PostgreSQL metadata, never Advbox calls."""

import hashlib
import hmac
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from jinja2 import Environment, StrictUndefined, select_autoescape
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from partner_reports.config import AppEnvironment
from partner_reports.pdf_imports.service import find_duplicate, receive_pdf
from partner_reports.pdf_imports.storage import LocalPrivatePdfStorage, PdfStorageUnavailable
from partner_reports.pdf_imports.validation import (
    MAX_PDF_BYTES,
    PdfRejected,
    validate_pdf,
    validate_upload_metadata,
)
from partner_reports.persistence.models import (
    AppUser,
    Partner,
    PdfImportBatch,
    PdfSourceDocument,
    PortalSession,
    ReportGenerationRequest,
    ReportVersion,
    SyncChangedPartner,
    SyncRun,
)
from partner_reports.web.artifacts import ArtifactUnavailable, SyntheticArtifactStore
from partner_reports.web.audit import emit_audit, record_audit, request_correlation_id
from partner_reports.web.security import (
    COOKIE_NAME,
    authenticated_user,
    clear_login_failures,
    find_credential,
    find_session,
    get_user_roles,
    login_is_limited,
    new_session,
    normalize_login,
    record_login_failure,
    revoke_session,
    verify_password,
)

router = APIRouter()
_TEMPLATES = Environment(
    autoescape=select_autoescape(default=True),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
_ASSETS = files("partner_reports.web")
_PAGE_SIZE = 10
_VERSION_LABELS = {
    "draft": "Rascunho",
    "validated": "Validado",
    "published": "Publicado",
    "superseded": "Substituído",
    "failed": "Erro",
}


def _db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as db:
        yield db


_DB_DEPENDENCY = Depends(_db)


def _render(template: str, **context) -> HTMLResponse:
    source = _ASSETS.joinpath("templates", template).read_text(encoding="utf-8")
    return HTMLResponse(_TEMPLATES.from_string(source).render(**context))


def _cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=8 * 60 * 60,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )


def _current(db: Session, request: Request) -> tuple[PortalSession | None, AppUser | None]:
    record = find_session(db, request.cookies.get(COOKIE_NAME))
    return record, authenticated_user(db, record)


def _need_user(db: Session, request: Request) -> tuple[PortalSession, AppUser]:
    record, user = _current(db, request)
    if record is None or user is None:
        raise HTTPException(status_code=401, detail="Acesso não autorizado")
    return record, user


async def _form(request: Request) -> dict[str, str]:
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=415, detail="Formulário inválido")
    declared_size = request.headers.get("content-length")
    if declared_size and declared_size.isdecimal() and int(declared_size) > 4096:
        raise HTTPException(status_code=413, detail="Formulário inválido")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4096:
            raise HTTPException(status_code=413, detail="Formulário inválido")
    try:
        parsed = parse_qs(body.decode("utf-8"), strict_parsing=True, max_num_fields=8)
    except (UnicodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Formulário inválido") from exc
    if any(len(values) != 1 for values in parsed.values()):
        raise HTTPException(status_code=400, detail="Formulário inválido")
    return {key: values[0] for key, values in parsed.items()}


def _csrf(form: dict[str, str], record: PortalSession | None) -> None:
    supplied = form.get("csrf", "")
    if record is None or not hmac.compare_digest(supplied, record.csrf_token):
        raise HTTPException(status_code=403, detail="Formulário expirado")


def _login_bucket(request: Request) -> str:
    # An opaque bucket is stored; raw network addresses are never persisted.
    client = request.client.host if request.client else "unknown"
    return hashlib.sha256(client.encode("utf-8")).hexdigest()


def _latest_versions(db: Session, partner_ids: list[uuid.UUID]) -> dict[uuid.UUID, ReportVersion]:
    if not partner_ids:
        return {}
    versions = db.scalars(
        select(ReportVersion)
        .where(ReportVersion.partner_id.in_(partner_ids))
        .order_by(ReportVersion.generated_at.desc(), ReportVersion.version.desc())
    )
    result: dict[uuid.UUID, ReportVersion] = {}
    for version in versions:
        result.setdefault(version.partner_id, version)
    return result


def _latest_requests(
    db: Session, partner_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ReportGenerationRequest]:
    if not partner_ids:
        return {}
    requests = db.scalars(
        select(ReportGenerationRequest)
        .where(ReportGenerationRequest.partner_id.in_(partner_ids))
        .order_by(ReportGenerationRequest.created_at.desc())
    )
    result: dict[uuid.UUID, ReportGenerationRequest] = {}
    for item in requests:
        result.setdefault(item.partner_id, item)
    return result


def _changed_at(db: Session, partner_ids: list[uuid.UUID]) -> dict[uuid.UUID, datetime]:
    if not partner_ids:
        return {}
    return dict(
        db.execute(
            select(SyncChangedPartner.partner_id, func.max(SyncRun.finished_at))
            .join(SyncRun, SyncRun.id == SyncChangedPartner.sync_run_id)
            .where(
                SyncChangedPartner.partner_id.in_(partner_ids),
                SyncRun.status == "succeeded",
            )
            .group_by(SyncChangedPartner.partner_id)
        ).all()
    )


def _status(
    version: ReportVersion | None,
    request: ReportGenerationRequest | None,
    changed_at: datetime | None,
) -> str:
    if version and request and request.created_at <= version.generated_at:
        request = None
    if request and request.status in {"pending", "running"}:
        return "gerando"
    if request and request.status == "failed":
        return "erro"
    if version is None:
        return "sem relatório"
    if version.status == "failed":
        return "erro"
    if version.status not in {"published", "validated"}:
        return "gerando"
    if changed_at and changed_at > version.generated_at:
        return "desatualizado"
    return "atualizado"


def _catalog(db: Session, query: str, status: str) -> list[dict]:
    partners = db.scalars(
        select(Partner)
        .where(Partner.status == "active", Partner.deleted_at.is_(None))
        .order_by(Partner.name, Partner.external_id)
    ).all()
    if query:
        q = query.casefold()
        partners = [p for p in partners if q in p.name.casefold() or q in p.external_id.casefold()]
    ids = [p.id for p in partners]
    versions = _latest_versions(db, ids)
    requests = _latest_requests(db, ids)
    changed = _changed_at(db, ids)
    rows = [
        {
            "partner": partner,
            "version": versions.get(partner.id),
            "status": _status(
                versions.get(partner.id), requests.get(partner.id), changed.get(partner.id)
            ),
        }
        for partner in partners
    ]
    return [row for row in rows if status == "todos" or row["status"] == status]


def _sync_at(db: Session) -> datetime | None:
    return db.scalar(select(func.max(SyncRun.finished_at)).where(SyncRun.status == "succeeded"))


def _require_partner(db: Session, partner_id: uuid.UUID) -> Partner:
    partner = db.get(Partner, partner_id)
    if partner is None or partner.status != "active" or partner.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Parceiro não encontrado")
    return partner


def _require_admin(db: Session, user: AppUser) -> None:
    if "portal_admin" not in get_user_roles(db, user.id):
        raise HTTPException(status_code=403, detail="Acesso não autorizado")


def _active_partners(db: Session) -> list[Partner]:
    return db.scalars(
        select(Partner)
        .where(Partner.status == "active", Partner.deleted_at.is_(None))
        .order_by(Partner.name, Partner.external_id)
    ).all()


def _upload_page(
    db: Session,
    user: AppUser,
    csrf: str,
    *,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    response = _render(
        "pdf_upload.html.j2",
        user=user,
        csrf=csrf,
        partners=_active_partners(db),
        error=error,
        max_mib=MAX_PDF_BYTES // (1024 * 1024),
    )
    response.status_code = status_code
    return response


async def _read_pdf_form(request: Request) -> tuple[dict[str, str], UploadFile, bytes]:
    if request.headers.get("content-type", "").split(";")[0] != "multipart/form-data":
        raise PdfRejected("FILE_NOT_PDF")
    declared_size = request.headers.get("content-length")
    if declared_size and declared_size.isdecimal() and int(declared_size) > MAX_PDF_BYTES + 1048576:
        raise PdfRejected("SIZE_LIMIT_EXCEEDED")
    try:
        form = await request.form(max_files=1, max_fields=8, max_part_size=MAX_PDF_BYTES + 1)
    except Exception as exc:
        raise PdfRejected("FILE_NOT_PDF") from exc
    expected = {"csrf", "partner_id", "period_start", "period_end", "source_pdf"}
    if set(form.keys()) != expected or any(len(form.getlist(key)) != 1 for key in expected):
        raise PdfRejected("FILE_NOT_PDF")
    upload = form.get("source_pdf")
    if not isinstance(upload, UploadFile):
        raise PdfRejected("FILE_NOT_PDF")
    validate_upload_metadata(upload.filename, upload.content_type)
    body = bytearray()
    try:
        while chunk := await upload.read(1024 * 1024):
            body.extend(chunk)
            if len(body) > MAX_PDF_BYTES:
                raise PdfRejected("SIZE_LIMIT_EXCEEDED")
    finally:
        await upload.close()
    fields = {key: str(form[key]) for key in expected - {"source_pdf"}}
    return fields, upload, bytes(body)


def _queue(db: Session, partner_id: uuid.UUID, user_id: uuid.UUID) -> None:
    # Lock the partner row, making duplicate requests for one partner serializable.
    db.scalar(select(Partner.id).where(Partner.id == partner_id).with_for_update())
    active = db.scalar(
        select(ReportGenerationRequest.id).where(
            ReportGenerationRequest.partner_id == partner_id,
            ReportGenerationRequest.status.in_(("pending", "running")),
        )
    )
    if active is None:
        db.add(
            ReportGenerationRequest(partner_id=partner_id, requested_by=user_id, status="pending")
        )
        db.flush()


def _audit_commit(
    db: Session,
    request: Request,
    action: str,
    *,
    actor_user_id: uuid.UUID | None = None,
    entity_type: str = "none",
    entity_id: uuid.UUID | None = None,
    reason_code: str | None = None,
) -> None:
    event = record_audit(
        db,
        action=action,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        reason_code=reason_code,
        correlation_id=request_correlation_id(request),
    )
    db.commit()
    emit_audit(event)


@router.get("/portal/assets.css")
def css() -> Response:
    content = _ASSETS.joinpath("assets", "portal.css").read_text(encoding="utf-8")
    return Response(content, media_type="text/css")


@router.get("/portal/login")
def login_page(request: Request, db: Session = _DB_DEPENDENCY) -> Response:
    _, user = _current(db, request)
    if user:
        return RedirectResponse("/portal/partners", status_code=303)
    old = find_session(db, request.cookies.get(COOKIE_NAME))
    token, record = new_session(db)
    revoke_session(db, old)
    db.commit()
    response = _render("login.html.j2", csrf=record.csrf_token, error=None)
    _cookie(response, token)
    return response


@router.post("/portal/login")
async def login(request: Request, db: Session = _DB_DEPENDENCY) -> Response:
    form = await _form(request)
    old = find_session(db, request.cookies.get(COOKIE_NAME))
    _csrf(form, old)
    bucket = _login_bucket(request)
    if login_is_limited(db, bucket):
        _audit_commit(db, request, "login_limited", reason_code="rate_limited")
        raise HTTPException(status_code=429, detail="Tente novamente mais tarde")
    try:
        login_name = normalize_login(form.get("login", ""))
    except ValueError:
        login_name = ""
    credential, user = find_credential(db, login_name)
    password = form.get("password", "")
    accepted = (
        bool(user and user.status == "active")
        and verify_password(credential.password_hash if credential else None, password)
        and bool(get_user_roles(db, user.id) & {"portal_viewer", "portal_admin"})
    )
    if not accepted:
        # The credential helper verifies against a dummy hash for unknown accounts.
        if credential is None or user is None or user.status != "active":
            verify_password(None, password)
        record_login_failure(db, bucket)
        _audit_commit(db, request, "login_failed", reason_code="invalid_credentials")
        return _render("login.html.j2", csrf=old.csrf_token, error="Acesso não autorizado")
    clear_login_failures(db, bucket)
    user.last_login_at = datetime.now(UTC)
    revoke_session(db, old)
    token, _ = new_session(db, user.id)
    _audit_commit(
        db, request, "login_succeeded", actor_user_id=user.id, entity_type="user", entity_id=user.id
    )
    response = RedirectResponse("/portal/partners", status_code=303)
    _cookie(response, token)
    return response


@router.post("/portal/logout")
async def logout(request: Request, db: Session = _DB_DEPENDENCY) -> Response:
    record, user = _need_user(db, request)
    _csrf(await _form(request), record)
    revoke_session(db, record)
    _audit_commit(
        db, request, "logout", actor_user_id=user.id, entity_type="user", entity_id=user.id
    )
    response = RedirectResponse("/portal/login", status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/portal")
def portal_home() -> Response:
    return RedirectResponse("/portal/partners", status_code=303)


@router.get("/portal/partners")
def partners(
    request: Request,
    q: str = "",
    status: str = "todos",
    page: int = 1,
    db: Session = _DB_DEPENDENCY,
) -> Response:
    record, user = _need_user(db, request)
    if (
        len(q) > 100
        or status
        not in {"todos", "atualizado", "desatualizado", "gerando", "erro", "sem relatório"}
        or page < 1
    ):
        raise HTTPException(status_code=400, detail="Filtro inválido")
    rows = _catalog(db, q.strip(), status)
    total_pages = max(1, (len(rows) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    if page > total_pages:
        page = total_pages
    shown = rows[(page - 1) * _PAGE_SIZE : page * _PAGE_SIZE]
    response = _render(
        "partners.html.j2",
        user=user,
        csrf=record.csrf_token,
        rows=shown,
        query=q,
        status=status,
        page=page,
        total_pages=total_pages,
        total=len(rows),
        sync_at=_sync_at(db),
        is_admin="portal_admin" in get_user_roles(db, user.id),
        demo=request.app.state.settings.app_env is not AppEnvironment.PRODUCTION,
    )
    _audit_commit(db, request, "catalog_view", actor_user_id=user.id)
    return response


@router.get("/portal/partners/{partner_id}")
def partner_detail(
    partner_id: uuid.UUID, request: Request, db: Session = _DB_DEPENDENCY
) -> Response:
    record, user = _need_user(db, request)
    partner = _require_partner(db, partner_id)
    versions = db.scalars(
        select(ReportVersion)
        .where(ReportVersion.partner_id == partner.id)
        .order_by(ReportVersion.generated_at.desc(), ReportVersion.version.desc())
        .limit(20)
    ).all()
    latest = versions[0] if versions else None
    latest_request = _latest_requests(db, [partner.id]).get(partner.id)
    state = _status(latest, latest_request, _changed_at(db, [partner.id]).get(partner.id))
    response = _render(
        "detail.html.j2",
        user=user,
        csrf=record.csrf_token,
        partner=partner,
        versions=versions,
        version_labels=_VERSION_LABELS,
        state=state,
        sync_at=_sync_at(db),
        is_admin="portal_admin" in get_user_roles(db, user.id),
        demo=request.app.state.settings.app_env is not AppEnvironment.PRODUCTION,
    )
    _audit_commit(
        db,
        request,
        "partner_view",
        actor_user_id=user.id,
        entity_type="partner",
        entity_id=partner.id,
    )
    return response


@router.get("/portal/imports/new")
def pdf_upload_page(request: Request, db: Session = _DB_DEPENDENCY) -> Response:
    record, user = _need_user(db, request)
    _require_admin(db, user)
    return _upload_page(db, user, record.csrf_token)


@router.post("/portal/imports/new")
async def pdf_upload(request: Request, db: Session = _DB_DEPENDENCY) -> Response:
    record, user = _need_user(db, request)
    _require_admin(db, user)
    user_id = user.id
    csrf_token = record.csrf_token
    try:
        fields, _, content = await _read_pdf_form(request)
        _csrf(fields, record)
    except PdfRejected as exc:
        _audit_commit(
            db,
            request,
            "pdf_upload_rejected",
            actor_user_id=user_id,
            reason_code=exc.code,
        )
        return _upload_page(
            db,
            user,
            csrf_token,
            error="O arquivo não atende aos requisitos da importação.",
            status_code=400,
        )

    try:
        partner_id = uuid.UUID(fields["partner_id"])
        period_start = date.fromisoformat(fields["period_start"])
        period_end = date.fromisoformat(fields["period_end"])
        if period_end < period_start:
            raise ValueError
        partner = db.get(Partner, partner_id)
        if partner is None or partner.status != "active" or partner.deleted_at is not None:
            raise ValueError
    except (KeyError, ValueError):
        _audit_commit(
            db,
            request,
            "pdf_upload_rejected",
            actor_user_id=user_id,
            reason_code="SOURCE_SCOPE_INVALID",
        )
        return _upload_page(
            db,
            user,
            csrf_token,
            error="Parceiro ou período inválido.",
            status_code=400,
        )

    try:
        validated = validate_pdf(content)
    except PdfRejected as exc:
        _audit_commit(
            db,
            request,
            "pdf_upload_rejected",
            actor_user_id=user_id,
            entity_type="partner",
            entity_id=partner_id,
            reason_code=exc.code,
        )
        return _upload_page(
            db,
            user,
            csrf_token,
            error="O arquivo não atende aos requisitos da importação.",
            status_code=400,
        )

    storage: LocalPrivatePdfStorage = request.app.state.pdf_import_storage
    result = None
    try:
        result = receive_pdf(
            db,
            storage,
            validated,
            partner_id=partner_id,
            period_start=period_start,
            period_end=period_end,
            uploaded_by=user_id,
        )
        action = "pdf_upload_duplicate" if result.duplicate else "pdf_upload_succeeded"
        reason = "DUPLICATE_SOURCE" if result.duplicate else None
        event = record_audit(
            db,
            action=action,
            actor_user_id=user_id,
            entity_type="pdf_import_batch",
            entity_id=result.batch.id,
            reason_code=reason,
            correlation_id=request_correlation_id(request),
        )
        db.commit()
        emit_audit(event)
    except IntegrityError:
        db.rollback()
        duplicate = find_duplicate(db, validated.source_sha256)
        if duplicate is None:
            _audit_commit(
                db,
                request,
                "pdf_upload_failed",
                actor_user_id=user_id,
                reason_code="STORAGE_UNAVAILABLE",
            )
            return _upload_page(
                db,
                user,
                csrf_token,
                error="Não foi possível guardar o arquivo com segurança.",
                status_code=503,
            )
        _audit_commit(
            db,
            request,
            "pdf_upload_duplicate",
            actor_user_id=user_id,
            entity_type="pdf_import_batch",
            entity_id=duplicate.id,
            reason_code="DUPLICATE_SOURCE",
        )
        result = type("DuplicateResult", (), {"batch": duplicate, "duplicate": True})()
    except PdfStorageUnavailable:
        db.rollback()
        _audit_commit(
            db,
            request,
            "pdf_upload_failed",
            actor_user_id=user_id,
            entity_type="partner",
            entity_id=partner_id,
            reason_code="STORAGE_UNAVAILABLE",
        )
        return _upload_page(
            db,
            user,
            csrf_token,
            error="Não foi possível guardar o arquivo com segurança.",
            status_code=503,
        )
    except SQLAlchemyError:
        db.rollback()
        if result is not None and result.object_key:
            storage.delete(result.object_key)
        raise

    if result.duplicate:
        return _upload_page(
            db,
            user,
            csrf_token,
            error="Este arquivo já foi recebido e não criou um novo lote.",
            status_code=409,
        )
    return RedirectResponse(f"/portal/imports/{result.batch.id}", status_code=303)


@router.get("/portal/imports/{batch_id}")
def pdf_import_detail(
    batch_id: uuid.UUID, request: Request, db: Session = _DB_DEPENDENCY
) -> Response:
    record, user = _need_user(db, request)
    _require_admin(db, user)
    row = db.execute(
        select(PdfImportBatch, PdfSourceDocument, Partner)
        .join(PdfSourceDocument, PdfSourceDocument.id == PdfImportBatch.source_document_id)
        .join(Partner, Partner.id == PdfImportBatch.partner_id)
        .where(PdfImportBatch.id == batch_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Importação não encontrada")
    batch, source, partner = row
    return _render(
        "pdf_import_detail.html.j2",
        user=user,
        csrf=record.csrf_token,
        batch=batch,
        source=source,
        partner=partner,
    )


@router.post("/portal/partners/{partner_id}/open")
async def open_or_queue(
    partner_id: uuid.UUID, request: Request, db: Session = _DB_DEPENDENCY
) -> Response:
    record, user = _need_user(db, request)
    _csrf(await _form(request), record)
    _require_partner(db, partner_id)
    version = _latest_versions(db, [partner_id]).get(partner_id)
    if version and version.status in {"published", "validated"}:
        return RedirectResponse(
            f"/portal/partners/{partner_id}/versions/{version.id}/html", status_code=303
        )
    _queue(db, partner_id, user.id)
    _audit_commit(
        db,
        request,
        "generation_requested",
        actor_user_id=user.id,
        entity_type="partner",
        entity_id=partner_id,
    )
    return RedirectResponse(f"/portal/partners/{partner_id}", status_code=303)


@router.post("/portal/partners/{partner_id}/regenerate")
async def regenerate(
    partner_id: uuid.UUID, request: Request, db: Session = _DB_DEPENDENCY
) -> Response:
    record, user = _need_user(db, request)
    _csrf(await _form(request), record)
    if "portal_admin" not in get_user_roles(db, user.id):
        raise HTTPException(status_code=403, detail="Acesso não autorizado")
    _require_partner(db, partner_id)
    _queue(db, partner_id, user.id)
    _audit_commit(
        db,
        request,
        "generation_requested",
        actor_user_id=user.id,
        entity_type="partner",
        entity_id=partner_id,
    )
    return RedirectResponse(f"/portal/partners/{partner_id}", status_code=303)


@router.get("/portal/partners/{partner_id}/versions/{version_id}/{kind}")
def artifact(
    partner_id: uuid.UUID,
    version_id: uuid.UUID,
    kind: str,
    request: Request,
    db: Session = _DB_DEPENDENCY,
) -> Response:
    user = None
    try:
        _, user = _need_user(db, request)
        _require_partner(db, partner_id)
    except HTTPException:
        _audit_commit(
            db,
            request,
            "artifact_denied",
            actor_user_id=user.id if user else None,
            entity_type="partner",
            entity_id=partner_id,
            reason_code="access_denied",
        )
        raise
    version = db.get(ReportVersion, version_id)
    if (
        kind not in {"html", "pdf"}
        or version is None
        or version.partner_id != partner_id
        or version.status not in {"validated", "published"}
        or not version.storage_object_key
    ):
        _audit_commit(
            db,
            request,
            "artifact_denied",
            actor_user_id=user.id,
            entity_type="partner",
            entity_id=partner_id,
            reason_code="access_denied",
        )
        raise HTTPException(status_code=404, detail="Versão não disponível")
    store: SyntheticArtifactStore = request.app.state.artifact_store
    try:
        content = store.read(version.storage_object_key, kind)
    except ArtifactUnavailable as exc:
        _audit_commit(
            db,
            request,
            "artifact_denied",
            actor_user_id=user.id,
            entity_type="partner",
            entity_id=partner_id,
            reason_code="access_denied",
        )
        raise HTTPException(status_code=404, detail="Versão não disponível") from exc
    _audit_commit(
        db,
        request,
        "report_view" if kind == "html" else "report_download",
        actor_user_id=user.id,
        entity_type="report_version",
        entity_id=version.id,
    )
    if kind == "html":
        return Response(
            content,
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"
            },
        )
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="relatorio-v{version.version}.pdf"'},
    )


def install_portal(app) -> None:
    engine = create_engine(app.state.settings.database_url.get_secret_value(), pool_pre_ping=True)
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.state.artifact_store = SyntheticArtifactStore(Path("output"), app.state.settings.app_env)
    app.state.pdf_import_storage = LocalPrivatePdfStorage(
        app.state.settings.pdf_storage_root, app.state.settings.app_env
    )
    app.include_router(router)

    @app.exception_handler(StarletteHTTPException)
    async def portal_http_error(request: Request, exc: StarletteHTTPException):
        if not request.url.path.startswith("/portal"):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        titles = {
            400: "Solicitação inválida",
            401: "Acesso necessário",
            403: "Acesso não autorizado",
            404: "Página indisponível",
            413: "Formulário inválido",
            415: "Formulário inválido",
            429: "Muitas tentativas",
        }
        title = titles.get(exc.status_code, "Não foi possível continuar")
        response = _render(
            "error.html.j2",
            code=exc.status_code,
            title=title,
            message="Verifique o acesso ou tente novamente mais tarde.",
        )
        response.status_code = exc.status_code
        return response

    @app.exception_handler(RequestValidationError)
    async def portal_validation_error(request: Request, exc: RequestValidationError):
        if not request.url.path.startswith("/portal"):
            return JSONResponse({"detail": "Solicitação inválida"}, status_code=422)
        response = _render(
            "error.html.j2",
            code=400,
            title="Solicitação inválida",
            message="Verifique o endereço ou os filtros e tente novamente.",
        )
        response.status_code = 400
        return response

    @app.exception_handler(Exception)
    async def portal_server_error(request: Request, exc: Exception):
        if not request.url.path.startswith("/portal"):
            return JSONResponse({"detail": "Erro interno"}, status_code=500)
        response = _render(
            "error.html.j2",
            code=500,
            title="Não foi possível continuar",
            message="Tente novamente mais tarde ou procure o responsável operacional.",
        )
        response.status_code = 500
        return response

    @app.middleware("http")
    async def portal_headers(request: Request, call_next):
        request_correlation_id(request)
        response = await call_next(request)
        if request.url.path.startswith("/portal"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
            if request.app.state.settings.is_production:
                response.headers["Strict-Transport-Security"] = (
                    "max-age=31536000; includeSubDomains"
                )
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; form-action 'self'; frame-ancestors 'none'",
            )
        return response

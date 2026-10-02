"""Authenticated internal portal backed by PostgreSQL metadata, never Advbox calls."""

import hashlib
import hmac
import secrets
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from importlib.resources import files
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from jinja2 import Environment, FunctionLoader, StrictUndefined, select_autoescape
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from partner_reports.config import Settings
from partner_reports.jobs.pdf_batch_reports import enqueue_approved_batch
from partner_reports.partner_scope import SYNTHETIC_PREFIX, partner_in_scope, partner_scope_clause
from partner_reports.pdf_imports.reporting import BatchReportUnavailable
from partner_reports.pdf_imports.review_service import (
    ReviewConflict,
    approve_batch,
    correct_item,
    reject_batch,
    reprocessing_pending,
    request_reprocessing,
)
from partner_reports.pdf_imports.service import find_duplicate, receive_pdf
from partner_reports.pdf_imports.storage import (
    PdfStorageUnavailable,
    PrivatePdfStorage,
    build_pdf_storage,
)
from partner_reports.pdf_imports.validation import (
    MAX_PDF_BYTES,
    PdfRejected,
    validate_pdf,
    validate_upload_metadata,
)
from partner_reports.persistence.models import (
    AppUser,
    Lawsuit,
    Partner,
    PdfImportBatch,
    PdfImportReview,
    PdfManifestItem,
    PdfReconciliationItem,
    PdfReconciliationRun,
    PdfSourceDocument,
    PortalCredential,
    PortalSession,
    ReportGenerationRequest,
    ReportVersion,
    SyncChangedPartner,
    SyncRun,
)
from partner_reports.web.accounts import (
    ACCESS_LINK_AGE,
    DISPLAY_NAME_MAX,
    AccountConflict,
    create_account,
    display_name,
    find_access_link,
    issue_access_link,
    list_accounts,
    redeem_access_link,
    set_active,
    set_admin,
)
from partner_reports.web.artifacts import (
    ArtifactUnavailable,
    SyntheticArtifactStore,
    build_artifact_store,
)
from partner_reports.web.audit import emit_audit, record_audit, request_correlation_id
from partner_reports.web.security import (
    COOKIE_NAME,
    MIN_PASSWORD_LENGTH,
    authenticated_user,
    clear_login_failures,
    find_credential,
    find_session,
    get_user_roles,
    hash_password,
    login_is_limited,
    new_session,
    normalize_login,
    record_login_failure,
    revoke_session,
    verify_password,
)

router = APIRouter()
_ASSETS = files("partner_reports.web")
_TEMPLATES = Environment(
    loader=FunctionLoader(
        lambda name: _ASSETS.joinpath("templates", name).read_text(encoding="utf-8")
    ),
    autoescape=select_autoescape(default=True),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
_LOCAL_ZONE = ZoneInfo("America/Sao_Paulo")
_BATCH_STATE_LABELS = {
    "all": "Todos",
    "uploaded": "Recebido",
    "quarantined": "Em conferência",
    "parsing": "Em conferência",
    "parsed": "Em conferência",
    "reconciling": "Em conferência",
    "needs_review": "Aguardando aprovação",
    "approved": "Aprovado",
    "rejected": "Descartado",
    "failed": "Falhou",
    "superseded": "Substituído",
}
_PROCESSING_LABELS = {
    "pending": "Na fila",
    "running": "Em andamento",
    "succeeded": "Concluído",
    "failed": "Falhou",
}


def _local(value: datetime) -> datetime:
    # Timestamps are stored in UTC; people read them in the office's time zone.
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(_LOCAL_ZONE)


def _format_datetime(value: datetime | None) -> str:
    return _local(value).strftime("%d/%m/%Y %H:%M") if value else "—"


def _format_date(value: date | datetime | None) -> str:
    if value is None:
        return "—"
    return (_local(value) if isinstance(value, datetime) else value).strftime("%d/%m/%Y")


_TEMPLATES.filters["datahora"] = _format_datetime
_TEMPLATES.filters["data"] = _format_date
_TEMPLATES.filters["estado"] = lambda value: _BATCH_STATE_LABELS.get(value, value)
_TEMPLATES.filters["processamento"] = lambda value: _PROCESSING_LABELS.get(value, value)
_TEMPLATES.filters["conferencia"] = lambda value: {
    "matched": "Conferido",
    "unmatched": "Não encontrado no Advbox",
    "ambiguous": "Ambíguo",
    "duplicate_source": "Repetido no PDF",
    "invalid_identifier": "Identificador inválido",
    "process_number_exact": "Número do processo",
    "folder_exact_unique": "Pasta",
}.get(value, value)
_TEMPLATES.filters["percentual"] = lambda value: (
    f"{value.normalize():f}".replace(".", ",") if value is not None else "—"
)
_TEMPLATES.filters["cnj"] = lambda value: (
    f"{value[:7]}-{value[7:9]}.{value[9:13]}.{value[13]}.{value[14:16]}.{value[16:]}"
    if value and len(value) == 20 and value.isdigit()
    else value
)
_PAGE_SIZE = 10
_PARTNER_NAME_MAX = 120
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
        .where(
            ReportVersion.partner_id.in_(partner_ids),
            ReportVersion.status.in_(("validated", "published")),
        )
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


_BATCH_NOTICES = {
    "geracao": "O envio foi aprovado, mas o relatório não pôde ser gerado agora.",
    "conflito": "A página estava desatualizada. Confira a situação abaixo e tente novamente.",
}


def _batch_stage(
    batch: PdfImportBatch,
    approval_blocked: bool,
    issues: list,
    version: ReportVersion | None,
    generation: ReportGenerationRequest | None,
) -> str:
    """One plain-language step of the upload → report flow."""

    if batch.state in {"rejected", "superseded"}:
        return batch.state
    if (
        batch.state == "approved"
        and generation is not None
        and generation.status in {"pending", "running"}
    ):
        return "generating"
    if version is not None and version.status in {"validated", "published"}:
        return "done"
    if batch.state == "failed" or (
        batch.state in {"quarantined", "parsed", "needs_review"}
        and batch.processing_status == "failed"
    ):
        return "failed"
    if batch.state == "needs_review":
        if batch.processing_status in {"pending", "running"}:
            return "processing"
        if issues:
            return "issues"
        return "blocked" if approval_blocked else "ready"
    if batch.state == "approved":
        if generation is not None and generation.status in {"pending", "running"}:
            return "generating"
        if generation is not None and generation.status == "failed":
            return "generation_failed"
        return "approved"
    return "processing"


def _work_queue(db: Session, settings: Settings) -> tuple[list[dict], list[dict]]:
    """Home dashboard: uploads needing a person and uploads the system is handling."""

    attention: list[dict] = []
    in_progress: list[dict] = []
    rows = db.execute(
        select(PdfImportBatch, Partner)
        .join(Partner, Partner.id == PdfImportBatch.partner_id)
        .where(
            partner_scope_clause(settings),
            PdfImportBatch.state.notin_(("rejected", "superseded", "failed")),
        )
        .order_by(PdfImportBatch.created_at.desc())
        .limit(30)
    ).all()
    for batch, partner in rows:
        item = {"batch": batch, "partner": partner}
        processing = batch.processing_status
        if processing == "failed" and batch.state in {"quarantined", "parsed", "needs_review"}:
            attention.append(
                {**item, "label": "A conferência no Advbox falhou", "action": "Tentar novamente"}
            )
        elif batch.state not in {"needs_review", "approved"} or processing in {
            "pending",
            "running",
        }:
            in_progress.append({**item, "label": "Conferindo no Advbox"})
        elif batch.state == "needs_review":
            run = db.scalar(
                select(PdfReconciliationRun)
                .where(PdfReconciliationRun.batch_id == batch.id)
                .order_by(PdfReconciliationRun.created_at.desc())
                .limit(1)
            )
            pending = (
                run.result_total - run.matched_count if run is not None else batch.parsed_item_count
            )
            if pending:
                attention.append(
                    {
                        **item,
                        "label": f"{pending} processo(s) precisam de correção",
                        "action": "Ver pendências",
                    }
                )
            else:
                attention.append(
                    {**item, "label": "Pronto para aprovar", "action": "Aprovar e gerar"}
                )
        else:
            generation = db.scalar(
                select(ReportGenerationRequest)
                .where(ReportGenerationRequest.pdf_batch_id == batch.id)
                .order_by(
                    ReportGenerationRequest.status.in_(("pending", "running")).desc(),
                    ReportGenerationRequest.created_at.desc(),
                )
                .limit(1)
            )
            if generation is not None and generation.status in {"pending", "running"}:
                in_progress.append({**item, "label": "Gerando o relatório"})
            elif generation is not None and generation.status == "failed":
                attention.append(
                    {**item, "label": "A geração do relatório falhou", "action": "Gerar novamente"}
                )
            elif (
                db.scalar(
                    select(ReportVersion.id)
                    .where(
                        ReportVersion.pdf_batch_id == batch.id,
                        ReportVersion.status.in_(("validated", "published")),
                    )
                    .limit(1)
                )
                is None
            ):
                attention.append(
                    {
                        **item,
                        "label": "Aprovado, relatório ainda não gerado",
                        "action": "Gerar relatório",
                    }
                )
    return attention, in_progress


def _catalog(db: Session, query: str, status: str, settings: Settings) -> list[dict]:
    partners = db.scalars(
        select(Partner)
        .where(
            Partner.status == "active",
            Partner.deleted_at.is_(None),
            partner_scope_clause(settings),
        )
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


def _require_partner(db: Session, partner_id: uuid.UUID, settings: Settings) -> Partner:
    partner = db.get(Partner, partner_id)
    if (
        partner is None
        or partner.status != "active"
        or partner.deleted_at is not None
        or not partner_in_scope(settings, partner)
    ):
        raise HTTPException(status_code=404, detail="Parceiro não encontrado")
    return partner


def _require_admin(db: Session, user: AppUser) -> None:
    if "portal_admin" not in get_user_roles(db, user.id):
        raise HTTPException(status_code=403, detail="Acesso não autorizado")


_REPORT_ROLES = frozenset({"portal_viewer", "portal_admin"})


def _require_report_operator(db: Session, user: AppUser) -> None:
    # Both roles send PDFs, approve and generate reports (D-056); admins also manage
    # users, partners and version restores.
    if not get_user_roles(db, user.id) & _REPORT_ROLES:
        raise HTTPException(status_code=403, detail="Acesso não autorizado")


def _active_partners(db: Session, settings: Settings) -> list[Partner]:
    return db.scalars(
        select(Partner)
        .where(
            Partner.status == "active",
            Partner.deleted_at.is_(None),
            partner_scope_clause(settings),
        )
        .order_by(Partner.name, Partner.external_id)
    ).all()


def _ready_reports(db: Session, settings: Settings, limit: int = 100) -> list[dict]:
    """Most recent validated or published versions of active partners, newest first."""

    return [
        {"version": version, "partner": partner}
        for version, partner in db.execute(
            select(ReportVersion, Partner)
            .join(Partner, Partner.id == ReportVersion.partner_id)
            .where(
                partner_scope_clause(settings),
                Partner.status == "active",
                Partner.deleted_at.is_(None),
                ReportVersion.status.in_(("validated", "published")),
            )
            .order_by(ReportVersion.generated_at.desc())
            .limit(limit)
        ).all()
    ]


def _nav(db: Session, user: AppUser, settings: Settings, active: str) -> dict:
    roles = get_user_roles(db, user.id)
    is_admin = "portal_admin" in roles
    return {
        "nav": active,
        "is_admin": is_admin,
        "can_report": bool(roles & _REPORT_ROLES),
        "partner_admin_link": is_admin and not settings.synthetic_validation_only,
    }


def _today() -> date:
    return datetime.now(_LOCAL_ZONE).date()


def _month_period(value: str) -> tuple[date, date]:
    # A month still in progress ends today: the official read must not precede it (D-053).
    start = date.fromisoformat(f"{value}-01")
    today = _today()
    if start > today:
        raise ValueError
    following = date(start.year + start.month // 12, start.month % 12 + 1, 1)
    end = date.fromordinal(following.toordinal() - 1)
    return start, min(end, today)


_MONTH_NAMES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def _recent_months(count: int = 12) -> list[dict[str, str]]:
    """Month options for the upload form, newest first (the browser picker is not themable)."""

    today = _today()
    months = []
    year, month = today.year, today.month
    for _ in range(count):
        label = f"{_MONTH_NAMES[month - 1].capitalize()} de {year:04d}"
        if (year, month) == (today.year, today.month):
            label += " (até hoje)"
        months.append({"value": f"{year:04d}-{month:02d}", "label": label})
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return months


def _upload_page(
    db: Session,
    user: AppUser,
    csrf: str,
    settings: Settings,
    *,
    selected: uuid.UUID | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    response = _render(
        "pdf_upload.html.j2",
        user=user,
        csrf=csrf,
        partners=_active_partners(db, settings),
        selected=selected,
        months=_recent_months(),
        error=error,
        max_mib=MAX_PDF_BYTES // (1024 * 1024),
        **_nav(db, user, settings, "new"),
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
    expected = {"csrf", "partner_id", "period_month", "source_pdf"}
    if set(form.keys()) != expected:
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


@router.get("/portal/assets.js")
def js() -> Response:
    content = _ASSETS.joinpath("assets", "portal.js").read_text(encoding="utf-8")
    return Response(content, media_type="text/javascript")


@router.get("/portal/login")
def login_page(request: Request, senha: str = "", db: Session = _DB_DEPENDENCY) -> Response:
    _, user = _current(db, request)
    if user:
        return RedirectResponse("/portal/partners", status_code=303)
    old = find_session(db, request.cookies.get(COOKIE_NAME))
    token, record = new_session(db)
    revoke_session(db, old)
    db.commit()
    response = _render(
        "login.html.j2",
        csrf=record.csrf_token,
        error=None,
        notice="Senha definida. Entre com o seu login." if senha == "definida" else None,
    )
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


def _password_page(
    db: Session,
    user: AppUser,
    csrf: str,
    *,
    changed: bool = False,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    credential = db.scalar(select(PortalCredential).where(PortalCredential.user_id == user.id))
    response = _render(
        "account_password.html.j2",
        csrf=csrf,
        login_name=credential.login_name if credential else "",
        min_length=MIN_PASSWORD_LENGTH,
        changed=changed,
        error=error,
    )
    response.status_code = status_code
    return response


@router.get("/portal/account/password")
def password_page(request: Request, alterada: int = 0, db: Session = _DB_DEPENDENCY) -> Response:
    record, user = _need_user(db, request)
    return _password_page(db, user, record.csrf_token, changed=alterada == 1)


@router.post("/portal/account/password")
async def change_password(request: Request, db: Session = _DB_DEPENDENCY) -> Response:
    record, user = _need_user(db, request)
    form = await _form(request)
    _csrf(form, record)
    # Same limiter as login: a stolen session must not become a password oracle.
    bucket = _login_bucket(request)
    if login_is_limited(db, bucket):
        _audit_commit(
            db,
            request,
            "password_change_failed",
            actor_user_id=user.id,
            entity_type="user",
            entity_id=user.id,
            reason_code="rate_limited",
        )
        raise HTTPException(status_code=429, detail="Tente novamente mais tarde")
    credential = db.scalar(
        select(PortalCredential).where(PortalCredential.user_id == user.id).with_for_update()
    )
    current = form.get("current_password", "")
    new = form.get("new_password", "")
    if credential is None or not verify_password(credential.password_hash, current):
        record_login_failure(db, bucket)
        _audit_commit(
            db,
            request,
            "password_change_failed",
            actor_user_id=user.id,
            entity_type="user",
            entity_id=user.id,
            reason_code="invalid_credentials",
        )
        return _password_page(
            db, user, record.csrf_token, error="Senha atual incorreta.", status_code=400
        )
    error = None
    if new != form.get("confirm_password", ""):
        error = "A confirmação não coincide com a nova senha."
    elif new == current:
        error = "A nova senha deve ser diferente da atual."
    else:
        try:
            credential.password_hash = hash_password(new)
        except ValueError:
            error = f"A nova senha deve ter entre {MIN_PASSWORD_LENGTH} e 256 caracteres."
    if error:
        db.rollback()
        return _password_page(db, user, record.csrf_token, error=error, status_code=400)
    clear_login_failures(db, bucket)
    # Every other session of this account ends; the current browser gets a fresh one.
    db.execute(delete(PortalSession).where(PortalSession.user_id == user.id))
    token, _ = new_session(db, user.id)
    _audit_commit(
        db,
        request,
        "password_changed",
        actor_user_id=user.id,
        entity_type="user",
        entity_id=user.id,
    )
    response = RedirectResponse("/portal/account/password?alterada=1", status_code=303)
    _cookie(response, token)
    return response


@router.get("/", include_in_schema=False)
def site_root() -> Response:
    # The login page forwards an authenticated session to the catalog.
    return RedirectResponse("/portal/login", status_code=303)


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
    rows = _catalog(db, q.strip(), status, request.app.state.settings)
    total_pages = max(1, (len(rows) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    if page > total_pages:
        page = total_pages
    shown = rows[(page - 1) * _PAGE_SIZE : page * _PAGE_SIZE]
    settings = request.app.state.settings
    nav = _nav(db, user, settings, "partners")
    attention, in_progress = _work_queue(db, settings)
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
        demo=settings.synthetic_validation_only,
        attention=attention if nav["can_report"] else [],
        in_progress=in_progress if nav["can_report"] else [],
        upload_partners=_active_partners(db, settings) if nav["can_report"] else [],
        months=_recent_months(),
        selected=None,
        max_mib=MAX_PDF_BYTES // (1024 * 1024),
        **nav,
    )
    _audit_commit(db, request, "catalog_view", actor_user_id=user.id)
    return response


@router.get("/portal/reports")
def ready_reports(request: Request, db: Session = _DB_DEPENDENCY) -> Response:
    record, user = _need_user(db, request)
    settings = request.app.state.settings
    response = _render(
        "reports.html.j2",
        user=user,
        csrf=record.csrf_token,
        ready=_ready_reports(db, settings),
        demo=settings.synthetic_validation_only,
        **_nav(db, user, settings, "reports"),
    )
    _audit_commit(db, request, "catalog_view", actor_user_id=user.id)
    return response


@router.get("/portal/partners/{partner_id}")
def partner_detail(
    partner_id: uuid.UUID, request: Request, db: Session = _DB_DEPENDENCY
) -> Response:
    record, user = _need_user(db, request)
    partner = _require_partner(db, partner_id, request.app.state.settings)
    versions = db.scalars(
        select(ReportVersion)
        .where(ReportVersion.partner_id == partner.id)
        .order_by(ReportVersion.generated_at.desc(), ReportVersion.version.desc())
        .limit(20)
    ).all()
    latest = next((row for row in versions if row.status in {"validated", "published"}), None)
    latest_request = _latest_requests(db, [partner.id]).get(partner.id)
    state = _status(latest, latest_request, _changed_at(db, [partner.id]).get(partner.id))
    batches = db.scalars(
        select(PdfImportBatch)
        .where(PdfImportBatch.partner_id == partner.id)
        .order_by(PdfImportBatch.created_at.desc(), PdfImportBatch.id.desc())
        .limit(5)
    ).all()
    response = _render(
        "detail.html.j2",
        user=user,
        csrf=record.csrf_token,
        partner=partner,
        versions=versions,
        latest_valid=latest,
        version_labels=_VERSION_LABELS,
        state=state,
        batches=batches,
        demo=request.app.state.settings.synthetic_validation_only,
        **_nav(db, user, request.app.state.settings, "partners"),
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
def pdf_upload_page(
    request: Request, parceiro: uuid.UUID | None = None, db: Session = _DB_DEPENDENCY
) -> Response:
    record, user = _need_user(db, request)
    _require_report_operator(db, user)
    return _upload_page(db, user, record.csrf_token, request.app.state.settings, selected=parceiro)


@router.post("/portal/imports/new")
async def pdf_upload(request: Request, db: Session = _DB_DEPENDENCY) -> Response:
    record, user = _need_user(db, request)
    _require_report_operator(db, user)
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
            request.app.state.settings,
            error="O arquivo não atende aos requisitos da importação.",
            status_code=400,
        )

    try:
        partner_id = uuid.UUID(fields["partner_id"])
        if "period_month" in fields:
            period_start, period_end = _month_period(fields["period_month"])
        else:
            period_start = date.fromisoformat(fields["period_start"])
            period_end = date.fromisoformat(fields["period_end"])
        if period_end < period_start:
            raise ValueError
        partner = db.get(Partner, partner_id)
        if (
            partner is None
            or partner.status != "active"
            or partner.deleted_at is not None
            or not partner_in_scope(request.app.state.settings, partner)
        ):
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
            request.app.state.settings,
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
            request.app.state.settings,
            error="O arquivo não atende aos requisitos da importação.",
            status_code=400,
        )

    storage: PrivatePdfStorage = request.app.state.pdf_import_storage
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
                request.app.state.settings,
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
            request.app.state.settings,
            error="Não foi possível guardar o arquivo com segurança.",
            status_code=503,
        )
    except SQLAlchemyError:
        db.rollback()
        if result is not None and result.object_key:
            storage.delete(result.object_key)
        raise

    if result.duplicate:
        existing = db.get(Partner, result.batch.partner_id)
        if existing is not None and partner_in_scope(request.app.state.settings, existing):
            return RedirectResponse(
                f"/portal/imports/{result.batch.id}?repetido=1", status_code=303
            )
        return _upload_page(
            db,
            user,
            csrf_token,
            request.app.state.settings,
            error="Este arquivo já foi recebido e não criou um novo lote.",
            status_code=409,
        )
    return RedirectResponse(f"/portal/imports/{result.batch.id}", status_code=303)


@router.get("/portal/imports")
def pdf_import_list(
    request: Request,
    partner_id: uuid.UUID | None = None,
    state: str = "all",
    period_start: date | None = None,
    period_end: date | None = None,
    page: int = 1,
    db: Session = _DB_DEPENDENCY,
) -> Response:
    record, user = _need_user(db, request)
    _require_report_operator(db, user)
    allowed = {
        "all",
        "uploaded",
        "quarantined",
        "parsing",
        "parsed",
        "reconciling",
        "needs_review",
        "approved",
        "rejected",
        "failed",
        "superseded",
    }
    if (
        state not in allowed
        or page < 1
        or (period_start and period_end and period_end < period_start)
    ):
        raise HTTPException(status_code=400, detail="Filtro inválido")
    query = (
        select(PdfImportBatch, Partner)
        .join(Partner, Partner.id == PdfImportBatch.partner_id)
        .where(partner_scope_clause(request.app.state.settings))
    )
    if partner_id:
        query = query.where(PdfImportBatch.partner_id == partner_id)
    if state != "all":
        query = query.where(PdfImportBatch.state == state)
    if period_start:
        query = query.where(PdfImportBatch.period_end >= period_start)
    if period_end:
        query = query.where(PdfImportBatch.period_start <= period_end)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(
        query.order_by(PdfImportBatch.created_at.desc(), PdfImportBatch.id.desc())
        .offset((page - 1) * _PAGE_SIZE)
        .limit(_PAGE_SIZE)
    ).all()
    runs = {}
    for batch, _ in rows:
        runs[batch.id] = db.scalar(
            select(PdfReconciliationRun)
            .where(PdfReconciliationRun.batch_id == batch.id)
            .order_by(PdfReconciliationRun.created_at.desc(), PdfReconciliationRun.id.desc())
            .limit(1)
        )
    return _render(
        "pdf_import_list.html.j2",
        user=user,
        csrf=record.csrf_token,
        rows=rows,
        runs=runs,
        partners=_active_partners(db, request.app.state.settings),
        state=state,
        partner_id=partner_id,
        period_start=period_start,
        period_end=period_end,
        page=page,
        total=total,
        pages=max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE),
        **_nav(db, user, request.app.state.settings, "imports"),
    )


@router.get("/portal/imports/{batch_id}")
def pdf_import_detail(
    batch_id: uuid.UUID,
    request: Request,
    repetido: int = 0,
    aviso: str = "",
    db: Session = _DB_DEPENDENCY,
) -> Response:
    record, user = _need_user(db, request)
    _require_report_operator(db, user)
    row = db.execute(
        select(PdfImportBatch, PdfSourceDocument, Partner)
        .join(PdfSourceDocument, PdfSourceDocument.id == PdfImportBatch.source_document_id)
        .join(Partner, Partner.id == PdfImportBatch.partner_id)
        .where(
            PdfImportBatch.id == batch_id,
            partner_scope_clause(request.app.state.settings),
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Importação não encontrada")
    batch, source, partner = row
    run = db.scalar(
        select(PdfReconciliationRun)
        .where(PdfReconciliationRun.batch_id == batch.id)
        .order_by(PdfReconciliationRun.created_at.desc(), PdfReconciliationRun.id.desc())
        .limit(1)
    )
    items = db.scalars(
        select(PdfReconciliationItem)
        .where(PdfReconciliationItem.run_id == run.id)
        .order_by(PdfReconciliationItem.id)
        if run
        else select(PdfReconciliationItem).where(False)
    ).all()
    reviews = db.scalars(
        select(PdfImportReview)
        .where(PdfImportReview.batch_id == batch.id)
        .order_by(PdfImportReview.review_revision.desc())
    ).all()
    replacements = db.scalars(
        select(PdfImportBatch).where(
            PdfImportBatch.partner_id == batch.partner_id,
            PdfImportBatch.period_start == batch.period_start,
            PdfImportBatch.period_end == batch.period_end,
            PdfImportBatch.state == "approved",
            PdfImportBatch.id != batch.id,
        )
    ).all()
    technical_ids = (
        db.scalars(
            select(Lawsuit.advbox_id)
            .where(Lawsuit.status == "active")
            .order_by(Lawsuit.advbox_id)
            .limit(500)
        ).all()
        if request.app.state.settings.pdf_synthetic_corrections
        and partner_in_scope(request.app.state.settings, partner)
        else []
    )
    corrected_ids = {
        review.reconciliation_item_id
        for review in reviews
        if review.decision == "corrected" and review.reconciliation_item_id is not None
    }
    manifest_flags = db.scalars(
        select(PdfManifestItem.quality_flags).where(PdfManifestItem.batch_id == batch.id)
    ).all()
    manifest_blocked = batch.parsed_item_count != len(manifest_flags) or any(
        set(flags) - {"page_continuation"} for flags in manifest_flags
    )
    pending_reprocess = run is not None and reprocessing_pending(db, batch, run)
    # A single earlier approval for the same month is replaced by "approve and generate".
    approval_blocked = (
        not run
        or not items
        or pending_reprocess
        or len(replacements) > 1
        or manifest_blocked
        or any(
            item.status != "matched"
            and not (
                technical_ids
                and item.status in {"unmatched", "ambiguous"}
                and item.id in corrected_ids
            )
            for item in items
        )
        or (request.app.state.settings.pdf_four_eyes and batch.uploaded_by == user.id)
    )
    manifest = {
        row.id: row
        for row in db.scalars(select(PdfManifestItem).where(PdfManifestItem.batch_id == batch.id))
    }
    issues = [
        (item, manifest.get(item.manifest_item_id))
        for item in items
        if item.status != "matched" and item.id not in corrected_ids
    ]
    version = db.scalar(
        select(ReportVersion)
        .where(ReportVersion.pdf_batch_id == batch.id)
        .order_by(ReportVersion.generated_at.desc())
        .limit(1)
    )
    # An active request wins over finished ones; otherwise the most recent one counts.
    generation = db.scalar(
        select(ReportGenerationRequest)
        .where(ReportGenerationRequest.pdf_batch_id == batch.id)
        .order_by(
            ReportGenerationRequest.status.in_(("pending", "running")).desc(),
            ReportGenerationRequest.created_at.desc(),
        )
        .limit(1)
    )
    stage = _batch_stage(batch, approval_blocked, issues, version, generation)
    return _render(
        "pdf_import_detail.html.j2",
        user=user,
        csrf=record.csrf_token,
        batch=batch,
        source=source,
        partner=partner,
        run=run,
        items=items,
        issues=issues,
        reviews=reviews,
        stage=stage,
        version=version,
        matched=sum(1 for item in items if item.status == "matched"),
        repeated=bool(repetido),
        notice=_BATCH_NOTICES.get(aviso),
        technical_ids=technical_ids,
        corrections_enabled=bool(technical_ids) and not pending_reprocess,
        **_nav(db, user, request.app.state.settings, "imports"),
    )


@router.post("/portal/imports/{batch_id}/review/{action}")
async def pdf_review_action(
    batch_id: uuid.UUID, action: str, request: Request, db: Session = _DB_DEPENDENCY
) -> Response:
    record, user = _need_user(db, request)
    _require_report_operator(db, user)
    form = await _form(request)
    _csrf(form, record)
    if form.get("confirm") != "yes" or action not in {
        "approve",
        "reject",
        "reprocess",
        "correct",
        "supersede",
    }:
        raise HTTPException(status_code=400, detail="Decisão inválida")
    try:
        revision = int(form["revision"])
        if revision < 0:
            raise ValueError
        environment = request.app.state.settings.app_env
        if action == "approve":
            approve_batch(
                db,
                batch_id,
                revision,
                user.id,
                environment=environment,
                four_eyes=request.app.state.settings.pdf_four_eyes,
                allow_corrections=request.app.state.settings.pdf_synthetic_corrections,
                settings=request.app.state.settings,
            )
            audit_action = "pdf_review_approved"
        elif action == "supersede":
            old_id = uuid.UUID(form["old_batch_id"])
            approve_batch(
                db,
                batch_id,
                revision,
                user.id,
                environment=environment,
                four_eyes=request.app.state.settings.pdf_four_eyes,
                allow_corrections=request.app.state.settings.pdf_synthetic_corrections,
                replace_batch_id=old_id,
                settings=request.app.state.settings,
            )
            audit_action = "pdf_review_superseded"
        elif action == "reject":
            reject_batch(
                db,
                batch_id,
                revision,
                user.id,
                environment=environment,
                settings=request.app.state.settings,
            )
            audit_action = "pdf_review_rejected"
        elif action == "reprocess":
            request_reprocessing(
                db,
                batch_id,
                revision,
                user.id,
                environment=environment,
                settings=request.app.state.settings,
            )
            audit_action = "pdf_review_reprocess_requested"
        else:
            correct_item(
                db,
                batch_id,
                uuid.UUID(form["item_id"]),
                int(form["advbox_id"]),
                revision,
                user.id,
                environment=environment,
                enabled=request.app.state.settings.pdf_synthetic_corrections,
                settings=request.app.state.settings,
            )
            audit_action = "pdf_review_corrected"
        event = record_audit(
            db,
            action=audit_action,
            actor_user_id=user.id,
            entity_type="pdf_import_batch",
            entity_id=batch_id,
            correlation_id=request_correlation_id(request),
        )
        db.commit()
        emit_audit(event)
    except (KeyError, ValueError, ReviewConflict) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Decisão inválida ou lote alterado") from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflito de vínculos") from exc
    return RedirectResponse(f"/portal/imports/{batch_id}", status_code=303)


@router.post("/portal/imports/{batch_id}/approve")
async def approve_and_generate(
    batch_id: uuid.UUID, request: Request, db: Session = _DB_DEPENDENCY
) -> Response:
    """Approve the upload (replacing a single earlier approval of the month) and queue it."""

    record, user = _need_user(db, request)
    _require_report_operator(db, user)
    form = await _form(request)
    _csrf(form, record)
    if form.get("confirm") != "yes":
        raise HTTPException(status_code=400, detail="Confirmação necessária")
    settings = request.app.state.settings
    page = f"/portal/imports/{batch_id}"
    try:
        revision = int(form["revision"])
        batch = db.get(PdfImportBatch, batch_id)
        if batch is None or revision < 0:
            raise ValueError
        earlier = db.scalars(
            select(PdfImportBatch.id).where(
                PdfImportBatch.partner_id == batch.partner_id,
                PdfImportBatch.period_start == batch.period_start,
                PdfImportBatch.period_end == batch.period_end,
                PdfImportBatch.state == "approved",
                PdfImportBatch.id != batch.id,
            )
        ).all()
        if len(earlier) > 1:
            raise ValueError
        approve_batch(
            db,
            batch_id,
            revision,
            user.id,
            environment=settings.app_env,
            four_eyes=settings.pdf_four_eyes,
            allow_corrections=settings.pdf_synthetic_corrections,
            replace_batch_id=earlier[0] if earlier else None,
            settings=settings,
        )
        event = record_audit(
            db,
            action="pdf_review_superseded" if earlier else "pdf_review_approved",
            actor_user_id=user.id,
            entity_type="pdf_import_batch",
            entity_id=batch_id,
            correlation_id=request_correlation_id(request),
        )
        db.commit()
        emit_audit(event)
    except (KeyError, ValueError, ReviewConflict, IntegrityError):
        db.rollback()
        return RedirectResponse(f"{page}?aviso=conflito", status_code=303)
    try:
        queued = enqueue_approved_batch(
            db,
            batch_id,
            environment=settings.app_env,
            requested_by=user.id,
            settings=settings,
        )
        event = None
        if queued:
            event = record_audit(
                db,
                action="generation_requested",
                actor_user_id=user.id,
                entity_type="pdf_import_batch",
                entity_id=batch_id,
                correlation_id=request_correlation_id(request),
            )
        db.commit()
        if event is not None:
            emit_audit(event)
    except (BatchReportUnavailable, IntegrityError):
        db.rollback()
        return RedirectResponse(f"{page}?aviso=geracao", status_code=303)
    return RedirectResponse(page, status_code=303)


@router.post("/portal/imports/{batch_id}/generate")
async def generate_from_pdf_batch(
    batch_id: uuid.UUID, request: Request, db: Session = _DB_DEPENDENCY
) -> Response:
    record, user = _need_user(db, request)
    _require_report_operator(db, user)
    form = await _form(request)
    _csrf(form, record)
    if form.get("confirm") != "yes":
        raise HTTPException(status_code=400, detail="Confirmação necessária")
    try:
        queued = enqueue_approved_batch(
            db,
            batch_id,
            environment=request.app.state.settings.app_env,
            requested_by=user.id,
            settings=request.app.state.settings,
        )
        if queued:
            event = record_audit(
                db,
                action="generation_requested",
                actor_user_id=user.id,
                entity_type="pdf_import_batch",
                entity_id=batch_id,
                correlation_id=request_correlation_id(request),
            )
        db.commit()
        if queued:
            emit_audit(event)
    except (BatchReportUnavailable, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Geração indisponível para este lote") from exc
    return RedirectResponse(f"/portal/imports/{batch_id}", status_code=303)


def _require_partner_admin(db: Session, request: Request) -> tuple[PortalSession, AppUser]:
    # Real partners exist only in the private pilot; synthetic runtimes never register them.
    record, user = _need_user(db, request)
    _require_admin(db, user)
    if request.app.state.settings.synthetic_validation_only:
        raise HTTPException(status_code=404, detail="Página não encontrada")
    return record, user


def _partner_admin_page(
    db: Session,
    user: AppUser,
    csrf: str,
    *,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    partners = db.scalars(
        select(Partner)
        .where(
            Partner.deleted_at.is_(None),
            ~Partner.external_id.startswith(SYNTHETIC_PREFIX),
            Partner.status == "active",
        )
        .order_by(Partner.name, Partner.external_id)
    ).all()
    response = _render(
        "partner_admin.html.j2",
        user=user,
        csrf=csrf,
        partners=partners,
        enabled=sum(1 for partner in partners if partner.pilot_enabled),
        error=error,
        max_name=_PARTNER_NAME_MAX,
        nav="admin",
        is_admin=True,
        can_report=True,
        partner_admin_link=True,
    )
    response.status_code = status_code
    return response


def _partner_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not 2 <= len(name) <= _PARTNER_NAME_MAX or not name.isprintable():
        raise ValueError
    return name


@router.get("/portal/admin/partners")
def partner_admin(request: Request, db: Session = _DB_DEPENDENCY) -> Response:
    record, user = _require_partner_admin(db, request)
    return _partner_admin_page(db, user, record.csrf_token)


@router.post("/portal/admin/partners")
async def create_partner(request: Request, db: Session = _DB_DEPENDENCY) -> Response:
    record, user = _require_partner_admin(db, request)
    form = await _form(request)
    _csrf(form, record)
    try:
        name = _partner_name(form.get("name", ""))
    except ValueError:
        return _partner_admin_page(
            db,
            user,
            record.csrf_token,
            error=f"Informe um nome com 2 a {_PARTNER_NAME_MAX} caracteres.",
            status_code=400,
        )
    # Opaque technical code: never derived from the name or any Advbox identifier.
    partner = Partner(
        external_id=f"PRT-{secrets.token_hex(5).upper()}",
        name=name,
        status="active",
        pilot_enabled=False,
    )
    db.add(partner)
    db.flush()
    _audit_commit(
        db,
        request,
        "partner_created",
        actor_user_id=user.id,
        entity_type="partner",
        entity_id=partner.id,
    )
    return RedirectResponse("/portal/admin/partners", status_code=303)


@router.post("/portal/admin/partners/{partner_id}/pilot/{action}")
async def set_partner_pilot(
    partner_id: uuid.UUID, action: str, request: Request, db: Session = _DB_DEPENDENCY
) -> Response:
    record, user = _require_partner_admin(db, request)
    form = await _form(request)
    _csrf(form, record)
    if form.get("confirm") != "yes" or action not in {"enable", "disable"}:
        raise HTTPException(status_code=400, detail="Confirmação necessária")
    partner = db.get(Partner, partner_id, with_for_update=True)
    if (
        partner is None
        or partner.deleted_at is not None
        or partner.status != "active"
        or partner.external_id.startswith(SYNTHETIC_PREFIX)
    ):
        raise HTTPException(status_code=404, detail="Parceiro não encontrado")
    enabled = action == "enable"
    if partner.pilot_enabled != enabled:
        partner.pilot_enabled = enabled
        _audit_commit(
            db,
            request,
            "partner_pilot_enabled" if enabled else "partner_pilot_disabled",
            actor_user_id=user.id,
            entity_type="partner",
            entity_id=partner.id,
        )
    else:
        db.rollback()
    return RedirectResponse("/portal/admin/partners", status_code=303)


def _percentage(raw: str) -> Decimal:
    value = Decimal(raw.strip().replace("%", "").replace(",", "."))
    if not value.is_finite() or not Decimal(0) <= value <= Decimal(100):
        raise ValueError
    return value.quantize(Decimal("0.01"))


@router.post("/portal/admin/partners/{partner_id}/percentage")
async def set_partner_percentage(
    partner_id: uuid.UUID, request: Request, db: Session = _DB_DEPENDENCY
) -> Response:
    """Each report version keeps the percentage it used; earlier versions never change."""

    record, user = _require_partner_admin(db, request)
    form = await _form(request)
    _csrf(form, record)
    back = form.get("back", "")
    target = back if back.startswith("/portal/imports/") and "//" not in back else None
    try:
        value = _percentage(form.get("percentage", ""))
    except (ArithmeticError, ValueError):
        return _partner_admin_page(
            db,
            user,
            record.csrf_token,
            error="Informe um percentual entre 0 e 100, por exemplo 10 ou 12,5.",
            status_code=400,
        )
    partner = db.get(Partner, partner_id, with_for_update=True)
    if (
        partner is None
        or partner.deleted_at is not None
        or partner.status != "active"
        or partner.external_id.startswith(SYNTHETIC_PREFIX)
    ):
        raise HTTPException(status_code=404, detail="Parceiro não encontrado")
    if partner.partnership_percentage != value:
        partner.partnership_percentage = value
        _audit_commit(
            db,
            request,
            "partner_percentage_changed",
            actor_user_id=user.id,
            entity_type="partner",
            entity_id=partner.id,
        )
    else:
        db.rollback()
    return RedirectResponse(target or "/portal/admin/partners", status_code=303)


@router.post("/portal/partners/{partner_id}/versions/{version_id}/restore")
async def restore_report_version(
    partner_id: uuid.UUID,
    version_id: uuid.UUID,
    request: Request,
    db: Session = _DB_DEPENDENCY,
) -> Response:
    record, user = _need_user(db, request)
    _require_admin(db, user)
    form = await _form(request)
    _csrf(form, record)
    if form.get("confirm") != "yes":
        raise HTTPException(status_code=400, detail="Confirmação necessária")
    _require_partner(db, partner_id, request.app.state.settings)
    db.scalar(select(Partner.id).where(Partner.id == partner_id).with_for_update())
    target = db.get(ReportVersion, version_id, with_for_update=True)
    if (
        target is None
        or target.partner_id != partner_id
        or target.status not in {"validated", "published", "superseded"}
        or not target.storage_object_key
    ):
        raise HTTPException(status_code=404, detail="Versão não disponível")
    store: SyntheticArtifactStore = request.app.state.artifact_store
    try:
        html = store.read(target.storage_object_key, "html")
        pdf = store.read(target.storage_object_key, "pdf")
        if target.pdf_batch_id is not None and (
            not target.content_sha256
            or hashlib.sha256(html + pdf).hexdigest() != target.content_sha256
        ):
            raise ArtifactUnavailable
    except ArtifactUnavailable as exc:
        raise HTTPException(status_code=404, detail="Versão não disponível") from exc
    newer = db.scalars(
        select(ReportVersion)
        .where(
            ReportVersion.partner_id == partner_id,
            ReportVersion.status.in_(("validated", "published")),
            ReportVersion.generated_at > target.generated_at,
        )
        .with_for_update()
    ).all()
    for row in newer:
        row.status = "superseded"
    target.status = "validated"
    event = record_audit(
        db,
        action="report_version_restored",
        actor_user_id=user.id,
        entity_type="report_version",
        entity_id=target.id,
        correlation_id=request_correlation_id(request),
    )
    db.commit()
    emit_audit(event)
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
        _require_partner(db, partner_id, request.app.state.settings)
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
        if version.pdf_batch_id is not None:
            html = content if kind == "html" else store.read(version.storage_object_key, "html")
            pdf = content if kind == "pdf" else store.read(version.storage_object_key, "pdf")
            if (
                not version.content_sha256
                or hashlib.sha256(html + pdf).hexdigest() != version.content_sha256
            ):
                raise ArtifactUnavailable
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
    app.state.artifact_store = build_artifact_store(
        app.state.settings.report_storage_root,
        app.state.settings.app_env,
        app.state.settings.pdf_data_scope,
    )
    app.state.pdf_import_storage = build_pdf_storage(
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
            if request.app.state.settings.is_deployed:
                response.headers["Strict-Transport-Security"] = (
                    "max-age=31536000; includeSubDomains"
                )
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; form-action 'self'; frame-ancestors 'none'",
            )
        return response


def _require_user_admin(db: Session, request: Request) -> tuple[PortalSession, AppUser]:
    record, user = _need_user(db, request)
    _require_admin(db, user)
    return record, user


def _users_page(
    db: Session,
    request: Request,
    user: AppUser,
    csrf: str,
    *,
    issued: dict | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    nav = _nav(db, user, request.app.state.settings, "users")
    response = _render(
        "user_admin.html.j2",
        user=user,
        csrf=csrf,
        accounts=list_accounts(db),
        issued=issued,
        error=error,
        max_name=DISPLAY_NAME_MAX,
        link_hours=int(ACCESS_LINK_AGE.total_seconds() // 3600),
        **nav,
    )
    response.status_code = status_code
    return response


def _issued(request: Request, token: str, target: AppUser, login_name: str, purpose: str) -> dict:
    return {
        "url": f"{str(request.base_url).rstrip('/')}/portal/access/{token}",
        "name": target.display_name or login_name,
        "login": login_name,
        "purpose": purpose,
    }


def _target_account(db: Session, user_id: uuid.UUID) -> tuple[AppUser, str]:
    target = db.get(AppUser, user_id, with_for_update=True)
    credential = db.scalar(select(PortalCredential).where(PortalCredential.user_id == user_id))
    if target is None or credential is None:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    return target, credential.login_name


@router.get("/portal/admin/users")
def user_admin(request: Request, db: Session = _DB_DEPENDENCY) -> Response:
    record, user = _require_user_admin(db, request)
    return _users_page(db, request, user, record.csrf_token)


@router.post("/portal/admin/users")
async def create_user(request: Request, db: Session = _DB_DEPENDENCY) -> Response:
    record, user = _require_user_admin(db, request)
    form = await _form(request)
    _csrf(form, record)
    try:
        name = display_name(form.get("name", ""))
        try:
            login_name = normalize_login(form.get("login", ""))
        except ValueError:
            raise AccountConflict(
                "O login deve ter 3 a 80 caracteres: letras minúsculas, números, ponto, "
                "hífen ou sublinhado."
            ) from None
        target, token, _ = create_account(
            db, user, login_name=login_name, name=name, admin=form.get("role") == "admin"
        )
    except AccountConflict as exc:
        db.rollback()
        return _users_page(db, request, user, record.csrf_token, error=str(exc), status_code=400)
    for action in ("account_created", "access_link_issued"):
        _audit_commit(
            db, request, action, actor_user_id=user.id, entity_type="user", entity_id=target.id
        )
    return _users_page(
        db,
        request,
        user,
        record.csrf_token,
        issued=_issued(request, token, target, login_name, "invite"),
    )


@router.post("/portal/admin/users/{user_id}/link")
async def issue_user_link(
    user_id: uuid.UUID, request: Request, db: Session = _DB_DEPENDENCY
) -> Response:
    record, user = _require_user_admin(db, request)
    _csrf(await _form(request), record)
    target, login_name = _target_account(db, user_id)
    if target.id == user.id:
        db.rollback()
        return _users_page(
            db,
            request,
            user,
            record.csrf_token,
            error="Para trocar a sua senha, use “Senha” no topo da página.",
            status_code=400,
        )
    purpose = "invite" if target.last_login_at is None else "reset"
    try:
        token, _ = issue_access_link(db, target, user, purpose=purpose)
    except AccountConflict as exc:
        db.rollback()
        return _users_page(db, request, user, record.csrf_token, error=str(exc), status_code=400)
    _audit_commit(
        db,
        request,
        "access_link_issued",
        actor_user_id=user.id,
        entity_type="user",
        entity_id=target.id,
    )
    return _users_page(
        db,
        request,
        user,
        record.csrf_token,
        issued=_issued(request, token, target, login_name, purpose),
    )


@router.post("/portal/admin/users/{user_id}/{field}/{value}")
async def change_user(
    user_id: uuid.UUID, field: str, value: str, request: Request, db: Session = _DB_DEPENDENCY
) -> Response:
    record, user = _require_user_admin(db, request)
    _csrf(await _form(request), record)
    choices = {"status": {"active", "inactive"}, "role": {"admin", "viewer"}}
    if value not in choices.get(field, set()):
        raise HTTPException(status_code=404, detail="Página não encontrada")
    target, _ = _target_account(db, user_id)
    try:
        if field == "status":
            changed = set_active(db, target, user, active=value == "active")
            action = "account_enabled" if value == "active" else "account_disabled"
        else:
            changed = set_admin(db, target, user, admin=value == "admin")
            action = "account_role_changed"
    except AccountConflict as exc:
        db.rollback()
        return _users_page(db, request, user, record.csrf_token, error=str(exc), status_code=400)
    if changed:
        _audit_commit(
            db, request, action, actor_user_id=user.id, entity_type="user", entity_id=target.id
        )
    else:
        db.rollback()
    return RedirectResponse("/portal/admin/users", status_code=303)


def _access_page(
    csrf: str | None,
    *,
    token: str = "",
    login_name: str = "",
    purpose: str = "",
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    response = _render(
        "access_link.html.j2",
        csrf=csrf,
        token=token,
        login_name=login_name,
        purpose=purpose,
        valid=csrf is not None,
        min_length=MIN_PASSWORD_LENGTH,
        error=error,
    )
    response.status_code = status_code
    return response


@router.get("/portal/access/{token}")
def access_link_page(token: str, request: Request, db: Session = _DB_DEPENDENCY) -> Response:
    found = find_access_link(db, token)
    if found is None:
        db.rollback()
        return _access_page(None, status_code=404)
    link, _, login_name = found
    old = find_session(db, request.cookies.get(COOKIE_NAME))
    session_token, session = new_session(db)
    revoke_session(db, old)
    db.commit()
    response = _access_page(
        session.csrf_token, token=token, login_name=login_name, purpose=link.purpose
    )
    _cookie(response, session_token)
    return response


@router.post("/portal/access/{token}")
async def redeem_access(token: str, request: Request, db: Session = _DB_DEPENDENCY) -> Response:
    form = await _form(request)
    session = find_session(db, request.cookies.get(COOKIE_NAME))
    _csrf(form, session)
    found = find_access_link(db, token)
    if found is None:
        db.rollback()
        return _access_page(None, status_code=404)
    link, target, login_name = found
    password = form.get("new_password", "")
    error = None
    if password != form.get("confirm_password", ""):
        error = "A confirmação não coincide com a senha."
    else:
        try:
            redeem_access_link(db, link, password)
        except ValueError:
            error = f"A senha deve ter entre {MIN_PASSWORD_LENGTH} e 256 caracteres."
    if error:
        db.rollback()
        return _access_page(
            session.csrf_token,
            token=token,
            login_name=login_name,
            purpose=link.purpose,
            error=error,
            status_code=400,
        )
    revoke_session(db, session)
    _audit_commit(
        db,
        request,
        "access_link_redeemed",
        actor_user_id=target.id,
        entity_type="user",
        entity_id=target.id,
    )
    response = RedirectResponse("/portal/login?senha=definida", status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response

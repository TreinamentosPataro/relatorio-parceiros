"""Local portal identity, opaque DB sessions and form protections."""

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from partner_reports.persistence.models import (
    AppUser,
    PortalCredential,
    PortalLoginAttempt,
    PortalSession,
    Role,
    UserRole,
)

COOKIE_NAME = "__Host-partner-portal"
SESSION_AGE = timedelta(hours=8)
LOGIN_AGE = timedelta(minutes=20)
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_LIMIT = 5
_LOGIN_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{2,79}")
_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
_DUMMY_HASH = _HASHER.hash("synthetic-placeholder-password")


def normalize_login(value: str) -> str:
    login = value.strip().lower()
    if not _LOGIN_NAME.fullmatch(login):
        raise ValueError("identificador de acesso inválido")
    return login


def hash_password(password: str) -> str:
    if len(password) < 14 or len(password) > 256:
        raise ValueError("a senha deve ter entre 14 e 256 caracteres")
    return _HASHER.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    try:
        return _HASHER.verify(stored_hash or _DUMMY_HASH, password)
    except (InvalidHashError, VerificationError, ValueError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def new_session(db: Session, user_id=None) -> tuple[str, PortalSession]:
    token = secrets.token_urlsafe(32)
    current = datetime.now(UTC)
    record = PortalSession(
        token_hash=token_digest(token),
        user_id=user_id,
        csrf_token=secrets.token_hex(32),
        expires_at=current + (SESSION_AGE if user_id else LOGIN_AGE),
    )
    db.add(record)
    db.flush()
    return token, record


def find_session(db: Session, token: str | None) -> PortalSession | None:
    if not token or len(token) > 128 or not token.isascii():
        return None
    return db.scalar(
        select(PortalSession).where(
            PortalSession.token_hash == token_digest(token),
            PortalSession.expires_at > datetime.now(UTC),
        )
    )


def revoke_session(db: Session, record: PortalSession | None) -> None:
    if record is not None:
        db.delete(record)
        db.flush()


def get_user_roles(db: Session, user_id) -> set[str]:
    return set(
        db.scalars(
            select(Role.key)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
    )


def authenticated_user(db: Session, record: PortalSession | None) -> AppUser | None:
    if record is None or record.user_id is None:
        return None
    user = db.get(AppUser, record.user_id)
    if user is None or user.status != "active":
        return None
    if not get_user_roles(db, user.id) & {"portal_viewer", "portal_admin"}:
        return None
    return user


def login_is_limited(db: Session, bucket_hash: str) -> bool:
    attempt = db.scalar(
        select(PortalLoginAttempt)
        .where(PortalLoginAttempt.bucket_hash == bucket_hash)
        .with_for_update()
    )
    return bool(
        attempt
        and attempt.window_started_at > datetime.now(UTC) - LOGIN_WINDOW
        and attempt.failures >= LOGIN_LIMIT
    )


def record_login_failure(db: Session, bucket_hash: str) -> None:
    current = datetime.now(UTC)
    attempt = db.scalar(
        select(PortalLoginAttempt)
        .where(PortalLoginAttempt.bucket_hash == bucket_hash)
        .with_for_update()
    )
    if attempt is None:
        db.add(PortalLoginAttempt(bucket_hash=bucket_hash, window_started_at=current, failures=1))
    elif attempt.window_started_at <= current - LOGIN_WINDOW:
        attempt.window_started_at = current
        attempt.failures = 1
    else:
        attempt.failures += 1
    db.flush()


def clear_login_failures(db: Session, bucket_hash: str) -> None:
    db.execute(delete(PortalLoginAttempt).where(PortalLoginAttempt.bucket_hash == bucket_hash))


def find_credential(db: Session, login: str) -> tuple[PortalCredential | None, AppUser | None]:
    credential = db.scalar(select(PortalCredential).where(PortalCredential.login_name == login))
    return credential, db.get(AppUser, credential.user_id) if credential else None

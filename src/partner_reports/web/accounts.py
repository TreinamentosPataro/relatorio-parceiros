"""Portal account management by administrators, with one-time access links.

Administrators never see or choose another person's password: they hand over a
single-use link, and its holder defines the password. Only the SHA-256 of a link
token is stored.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from partner_reports.persistence.models import (
    AppUser,
    PortalAccessLink,
    PortalCredential,
    PortalSession,
    Role,
    UserRole,
)
from partner_reports.web.security import hash_password, token_digest

ACCESS_LINK_AGE = timedelta(hours=72)
ROLES = ("portal_viewer", "portal_admin")
DISPLAY_NAME_MAX = 120


class AccountConflict(ValueError):
    """A request that would break an account rule; the text is safe to show."""


@dataclass(frozen=True)
class AccountRow:
    user: AppUser
    login_name: str
    is_admin: bool
    pending_link: PortalAccessLink | None


def _unusable_password() -> str:
    # Nobody knows this value: the account is usable only after its link is redeemed.
    return hash_password(secrets.token_urlsafe(48))


def _role(db: Session, key: str) -> Role:
    role = db.scalar(select(Role).where(Role.key == key))
    if role is None:
        role = Role(key=key, description="Acesso interno ao portal")
        db.add(role)
        db.flush()
    return role


def _roles(db: Session, user_id: uuid.UUID) -> set[str]:
    return set(
        db.scalars(
            select(Role.key)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
    )


def _active_admins(db: Session) -> int:
    return db.scalar(
        select(func.count(func.distinct(AppUser.id)))
        .join(UserRole, UserRole.user_id == AppUser.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.key == "portal_admin", AppUser.status == "active")
    )


def display_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not 2 <= len(name) <= DISPLAY_NAME_MAX or not name.isprintable():
        raise AccountConflict(f"Informe um nome com 2 a {DISPLAY_NAME_MAX} caracteres.")
    return name


def list_accounts(db: Session) -> list[AccountRow]:
    now = datetime.now(UTC)
    rows = db.execute(
        select(AppUser, PortalCredential.login_name)
        .join(PortalCredential, PortalCredential.user_id == AppUser.id)
        .order_by(AppUser.status, func.lower(func.coalesce(AppUser.display_name, "")))
    ).all()
    result = []
    for user, login_name in rows:
        pending = db.scalar(
            select(PortalAccessLink)
            .where(
                PortalAccessLink.user_id == user.id,
                PortalAccessLink.used_at.is_(None),
                PortalAccessLink.expires_at > now,
            )
            .order_by(PortalAccessLink.created_at.desc())
            .limit(1)
        )
        result.append(AccountRow(user, login_name, "portal_admin" in _roles(db, user.id), pending))
    return result


def issue_access_link(
    db: Session, user: AppUser, actor: AppUser, *, purpose: str
) -> tuple[str, PortalAccessLink]:
    """Replace any open link of the account; a reset also locks the old password out."""

    if user.status != "active":
        raise AccountConflict("Reative a conta antes de gerar um link de acesso.")
    now = datetime.now(UTC)
    db.execute(
        update(PortalAccessLink)
        .where(PortalAccessLink.user_id == user.id, PortalAccessLink.used_at.is_(None))
        .values(expires_at=now)
    )
    if purpose == "reset":
        credential = db.scalar(
            select(PortalCredential).where(PortalCredential.user_id == user.id).with_for_update()
        )
        credential.password_hash = _unusable_password()
        db.execute(delete(PortalSession).where(PortalSession.user_id == user.id))
    token = secrets.token_urlsafe(32)
    link = PortalAccessLink(
        token_hash=token_digest(token),
        user_id=user.id,
        purpose=purpose,
        created_by_user_id=actor.id,
        expires_at=now + ACCESS_LINK_AGE,
    )
    db.add(link)
    db.flush()
    return token, link


def create_account(
    db: Session, actor: AppUser, *, login_name: str, name: str, admin: bool
) -> tuple[AppUser, str, PortalAccessLink]:
    if db.scalar(select(PortalCredential.id).where(PortalCredential.login_name == login_name)):
        raise AccountConflict("Este login já está em uso. Escolha outro.")
    user = AppUser(external_subject=f"local:{login_name}", display_name=name, status="active")
    db.add(user)
    db.flush()
    db.add(
        PortalCredential(user_id=user.id, login_name=login_name, password_hash=_unusable_password())
    )
    db.add(UserRole(user_id=user.id, role_id=_role(db, ROLES[admin]).id))
    db.flush()
    token, link = issue_access_link(db, user, actor, purpose="invite")
    return user, token, link


def set_active(db: Session, user: AppUser, actor: AppUser, *, active: bool) -> bool:
    if user.id == actor.id:
        raise AccountConflict("Você não pode desativar a própria conta.")
    if (user.status == "active") == active:
        return False
    if not active and "portal_admin" in _roles(db, user.id) and _active_admins(db) <= 1:
        raise AccountConflict("Mantenha pelo menos um administrador ativo.")
    user.status = "active" if active else "inactive"
    if not active:
        db.execute(delete(PortalSession).where(PortalSession.user_id == user.id))
        db.execute(
            update(PortalAccessLink)
            .where(PortalAccessLink.user_id == user.id, PortalAccessLink.used_at.is_(None))
            .values(expires_at=datetime.now(UTC))
        )
    return True


def set_admin(db: Session, user: AppUser, actor: AppUser, *, admin: bool) -> bool:
    if user.id == actor.id:
        raise AccountConflict("Peça a outro administrador para mudar o seu papel.")
    roles = _roles(db, user.id)
    if ("portal_admin" in roles) == admin:
        return False
    if not admin and user.status == "active" and _active_admins(db) <= 1:
        raise AccountConflict("Mantenha pelo menos um administrador ativo.")
    db.execute(delete(UserRole).where(UserRole.user_id == user.id))
    db.add(UserRole(user_id=user.id, role_id=_role(db, ROLES[admin]).id))
    # A new role takes effect at the next login.
    db.execute(delete(PortalSession).where(PortalSession.user_id == user.id))
    return True


def find_access_link(db: Session, token: str) -> tuple[PortalAccessLink, AppUser, str] | None:
    if not token or len(token) > 128 or not token.isascii():
        return None
    link = db.scalar(
        select(PortalAccessLink)
        .where(
            PortalAccessLink.token_hash == token_digest(token),
            PortalAccessLink.used_at.is_(None),
            PortalAccessLink.expires_at > datetime.now(UTC),
        )
        .with_for_update()
    )
    if link is None:
        return None
    user = db.get(AppUser, link.user_id)
    credential = db.scalar(select(PortalCredential).where(PortalCredential.user_id == link.user_id))
    if user is None or user.status != "active" or credential is None:
        return None
    return link, user, credential.login_name


def redeem_access_link(db: Session, link: PortalAccessLink, password: str) -> None:
    credential = db.scalar(
        select(PortalCredential).where(PortalCredential.user_id == link.user_id).with_for_update()
    )
    credential.password_hash = hash_password(password)
    link.used_at = datetime.now(UTC)
    db.execute(delete(PortalSession).where(PortalSession.user_id == link.user_id))

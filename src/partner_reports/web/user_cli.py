"""Interactive portal account bootstrap, revocation and session cleanup."""

import argparse
import getpass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select

from partner_reports.persistence.database import get_session_factory
from partner_reports.persistence.models import (
    AppUser,
    PortalCredential,
    PortalLoginAttempt,
    PortalSession,
    Role,
    UserRole,
)
from partner_reports.web.audit import emit_audit, record_audit
from partner_reports.web.security import (
    find_credential,
    get_user_roles,
    hash_password,
    normalize_login,
    verify_password,
)


def _admin_actor(db, actor_login: str | None) -> AppUser:
    if not actor_login:
        raise SystemExit("Informe --actor-login de administrador interno")
    credential, user = find_credential(db, normalize_login(actor_login))
    password = getpass.getpass("Senha do administrador: ")
    if (
        user is None
        or user.status != "active"
        or "portal_admin" not in get_user_roles(db, user.id)
        or not verify_password(credential.password_hash if credential else None, password)
    ):
        raise SystemExit("Administrador não autorizado")
    return user


def main() -> None:
    parser = argparse.ArgumentParser(description="Gerenciar contas internas do portal")
    parser.add_argument(
        "command", choices=("create", "disable", "revoke-sessions", "purge-expired")
    )
    parser.add_argument("--login", help="identificador técnico da conta, sem dados pessoais")
    parser.add_argument("--actor-login", help="identificador técnico do administrador executor")
    parser.add_argument(
        "--admin", action="store_true", help="conceder papel administrativo ao criar"
    )
    args = parser.parse_args()
    if args.command != "purge-expired" and not args.login:
        parser.error("--login é obrigatório")
    if args.admin and args.command != "create":
        parser.error("--admin só é válido em create")
    login = normalize_login(args.login) if args.login else None
    with get_session_factory()() as db, db.begin():
        bootstrap = args.command == "create" and not db.scalar(select(func.count(AppUser.id)))
        if bootstrap and not args.admin:
            raise SystemExit("A primeira conta interna deve ser administradora")
        actor = None if bootstrap else _admin_actor(db, args.actor_login)
        if args.command == "create":
            if db.scalar(select(PortalCredential.id).where(PortalCredential.login_name == login)):
                raise SystemExit("Identificador já cadastrado")
            password = getpass.getpass("Senha (mínimo de 14 caracteres): ")
            confirmation = getpass.getpass("Confirme a senha: ")
            if password != confirmation:
                raise SystemExit("Senhas não coincidem")
            user = AppUser(external_subject=f"local:{login}", status="active")
            db.add(user)
            db.flush()
            db.add(
                PortalCredential(
                    user_id=user.id, login_name=login, password_hash=hash_password(password)
                )
            )
            role_key = "portal_admin" if args.admin else "portal_viewer"
            role = db.scalar(select(Role).where(Role.key == role_key))
            if role is None:
                role = Role(key=role_key, description="Acesso interno ao portal")
                db.add(role)
                db.flush()
            db.add(UserRole(user_id=user.id, role_id=role.id))
            action = "account_created"
            target = user
        elif args.command in ("disable", "revoke-sessions"):
            credential = db.scalar(
                select(PortalCredential)
                .where(PortalCredential.login_name == login)
                .with_for_update()
            )
            if credential is None:
                raise SystemExit("Conta não encontrada")
            target = db.get(AppUser, credential.user_id, with_for_update=True)
            if target.id == actor.id:
                raise SystemExit("Use outro administrador para revogar a própria conta")
            if args.command == "disable":
                target.status = "inactive"
            db.execute(delete(PortalSession).where(PortalSession.user_id == target.id))
            action = "account_disabled" if args.command == "disable" else "sessions_revoked"
        else:
            now = datetime.now(UTC)
            db.execute(delete(PortalSession).where(PortalSession.expires_at <= now))
            db.execute(
                delete(PortalLoginAttempt).where(
                    PortalLoginAttempt.window_started_at < now - timedelta(days=15)
                )
            )
            action = "security_metadata_purged"
            target = None
        event = record_audit(
            db,
            action=action,
            actor_user_id=actor.id if actor else None,
            entity_type="user" if target else "none",
            entity_id=target.id if target else None,
        )
    emit_audit(event)
    print("Operação de conta concluída; nenhuma credencial foi exibida.")


if __name__ == "__main__":
    main()

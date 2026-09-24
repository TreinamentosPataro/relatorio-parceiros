"""Add persistent portal identity, sessions and generation requests.

Revision ID: 20260916_0003
Revises: 20260916_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260916_0003"
down_revision: str | None = "20260916_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portal_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("login_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portal_credentials")),
        sa.UniqueConstraint("user_id", name=op.f("uq_portal_credentials_user_id")),
        sa.UniqueConstraint("login_name", name=op.f("uq_portal_credentials_login_name")),
    )
    op.create_table(
        "portal_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portal_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_portal_sessions_token_hash")),
    )
    op.create_index(op.f("ix_portal_sessions_user_id"), "portal_sessions", ["user_id"])
    op.create_table(
        "portal_login_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bucket_hash", sa.String(64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portal_login_attempts")),
        sa.UniqueConstraint("bucket_hash", name=op.f("uq_portal_login_attempts_bucket_hash")),
    )
    op.create_table(
        "report_generation_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name=op.f("ck_report_generation_requests_status_values"),
        ),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_generation_requests")),
    )
    op.create_index(
        op.f("ix_report_generation_requests_partner_id"),
        "report_generation_requests",
        ["partner_id"],
    )


def downgrade() -> None:
    op.drop_table("report_generation_requests")
    op.drop_table("portal_login_attempts")
    op.drop_table("portal_sessions")
    op.drop_table("portal_credentials")

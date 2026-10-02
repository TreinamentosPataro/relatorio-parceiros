"""One-time invite and reset links so administrators manage accounts in the portal.

Revision ID: 20261002_0016
Revises: 20261001_0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261002_0016"
down_revision: str | None = "20261001_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portal_access_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(10), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "purpose IN ('invite', 'reset')", name=op.f("ck_portal_access_links_purpose_values")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_portal_access_links_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_portal_access_links_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portal_access_links")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_portal_access_links_token_hash")),
    )
    op.create_index(op.f("ix_portal_access_links_user_id"), "portal_access_links", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_portal_access_links_user_id"), table_name="portal_access_links")
    op.drop_table("portal_access_links")

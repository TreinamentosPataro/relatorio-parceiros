"""Add resumable reconciliation metadata and persisted partner invalidations.

Revision ID: 20260916_0002
Revises: 20260915_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260916_0002"
down_revision: str | None = "20260915_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("customers", "lawsuits", "transactions"):
        op.add_column(table, sa.Column("report_hash", sa.String(64), nullable=True))
    op.add_column("sync_runs", sa.Column("expected_total", sa.BigInteger(), nullable=True))
    op.add_column("sync_errors", sa.Column("page_offset", sa.BigInteger(), nullable=True))
    op.add_column(
        "sync_errors", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(op.f("ix_sync_errors_page_offset"), "sync_errors", ["page_offset"])
    op.create_table(
        "sync_changed_partners",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sync_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sync_run_id"], ["sync_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_changed_partners")),
        sa.UniqueConstraint(
            "sync_run_id", "partner_id", name="uq_sync_changed_partners_run_partner"
        ),
    )
    op.create_index(
        op.f("ix_sync_changed_partners_sync_run_id"), "sync_changed_partners", ["sync_run_id"]
    )
    op.create_index(
        op.f("ix_sync_changed_partners_partner_id"), "sync_changed_partners", ["partner_id"]
    )


def downgrade() -> None:
    op.drop_table("sync_changed_partners")
    op.drop_index(op.f("ix_sync_errors_page_offset"), table_name="sync_errors")
    op.drop_column("sync_errors", "resolved_at")
    op.drop_column("sync_errors", "page_offset")
    op.drop_column("sync_runs", "expected_total")
    for table in ("transactions", "lawsuits", "customers"):
        op.drop_column(table, "report_hash")

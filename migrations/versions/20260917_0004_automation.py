"""Persist local synthetic automation sources and leased report requests.

Revision ID: 20260917_0004
Revises: 20260916_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260917_0004"
down_revision: str | None = "20260916_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "synthetic_portfolios",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario", sa.String(10), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "scenario IN ('zero', 'one', 'many')",
            name=op.f("ck_synthetic_portfolios_scenario_values"),
        ),
        sa.CheckConstraint("revision > 0", name=op.f("ck_synthetic_portfolios_revision_positive")),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_synthetic_portfolios")),
        sa.UniqueConstraint("partner_id", name=op.f("uq_synthetic_portfolios_partner_id")),
    )
    op.add_column("report_versions", sa.Column("source_digest", sa.String(64)))
    op.add_column("report_versions", sa.Column("customer_count", sa.Integer()))
    op.add_column("report_versions", sa.Column("case_count", sa.Integer()))
    op.alter_column(
        "report_generation_requests",
        "requested_by",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.add_column(
        "report_generation_requests",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "report_generation_requests", sa.Column("available_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "report_generation_requests", sa.Column("lease_token", postgresql.UUID(as_uuid=True))
    )
    op.add_column(
        "report_generation_requests", sa.Column("lease_expires_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "report_generation_requests", sa.Column("heartbeat_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "report_generation_requests", sa.Column("finished_at", sa.DateTime(timezone=True))
    )
    op.add_column("report_generation_requests", sa.Column("error_code", sa.String(80)))
    op.add_column("report_generation_requests", sa.Column("source_digest", sa.String(64)))
    op.create_index(
        "uq_report_generation_requests_active_partner",
        "report_generation_requests",
        ["partner_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_report_generation_requests_active_partner", table_name="report_generation_requests"
    )
    for name in (
        "source_digest",
        "error_code",
        "finished_at",
        "heartbeat_at",
        "lease_expires_at",
        "lease_token",
        "available_at",
        "attempt_count",
    ):
        op.drop_column("report_generation_requests", name)
    op.alter_column(
        "report_generation_requests",
        "requested_by",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    for name in ("case_count", "customer_count", "source_digest"):
        op.drop_column("report_versions", name)
    op.drop_table("synthetic_portfolios")

"""Add a durable lease queue for PDF parsing and reconciliation.

Revision ID: 20260930_0013
Revises: 20260925_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260930_0013"
down_revision: str | None = "20260925_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pdf_import_batches",
        sa.Column(
            "processing_status", sa.String(length=20), server_default="pending", nullable=False
        ),
    )
    op.add_column(
        "pdf_import_batches",
        sa.Column("processing_attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "pdf_import_batches", sa.Column("processing_available_at", sa.DateTime(timezone=True))
    )
    op.add_column("pdf_import_batches", sa.Column("processing_lease_token", sa.Uuid()))
    op.add_column(
        "pdf_import_batches", sa.Column("processing_lease_expires_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "pdf_import_batches", sa.Column("processing_heartbeat_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "pdf_import_batches", sa.Column("processing_finished_at", sa.DateTime(timezone=True))
    )
    op.add_column("pdf_import_batches", sa.Column("processing_error_code", sa.String(length=80)))
    op.create_check_constraint(
        "ck_pdf_import_batches_processing_status_values",
        "pdf_import_batches",
        "processing_status IN ('pending', 'running', 'succeeded', 'failed')",
    )
    op.create_check_constraint(
        "ck_pdf_import_batches_processing_attempt_nonnegative",
        "pdf_import_batches",
        "processing_attempt_count >= 0",
    )
    op.create_index(
        "ix_pdf_import_batches_processing_queue",
        "pdf_import_batches",
        ["processing_status", "processing_available_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_pdf_import_batches_processing_queue", table_name="pdf_import_batches")
    op.drop_constraint(
        "ck_pdf_import_batches_processing_attempt_nonnegative",
        "pdf_import_batches",
        type_="check",
    )
    op.drop_constraint(
        "ck_pdf_import_batches_processing_status_values", "pdf_import_batches", type_="check"
    )
    for column in (
        "processing_error_code",
        "processing_finished_at",
        "processing_heartbeat_at",
        "processing_lease_expires_at",
        "processing_lease_token",
        "processing_available_at",
        "processing_attempt_count",
        "processing_status",
    ):
        op.drop_column("pdf_import_batches", column)

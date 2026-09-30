"""Persist only versioned, allowlisted PDF manifest items and counts.

Revision ID: 20260925_0006
Revises: 20260923_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260925_0006"
down_revision: str | None = "20260923_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pdf_import_batches", sa.Column("parsed_item_count", sa.Integer()))
    op.add_column("pdf_import_batches", sa.Column("parse_quality_count", sa.Integer()))
    op.add_column("pdf_import_batches", sa.Column("parsed_at", sa.DateTime(timezone=True)))
    op.create_table(
        "pdf_manifest_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_ordinal", sa.Integer(), nullable=False),
        sa.Column("process_number_normalized", sa.String(20)),
        sa.Column("folder_exact", sa.String(80)),
        sa.Column("source_page_start", sa.Integer(), nullable=False),
        sa.Column("source_page_end", sa.Integer(), nullable=False),
        sa.Column("quality_flags", postgresql.ARRAY(sa.String(40)), nullable=False),
        sa.CheckConstraint(
            "source_ordinal > 0", name=op.f("ck_pdf_manifest_items_source_ordinal_positive")
        ),
        sa.CheckConstraint(
            "source_page_start > 0", name=op.f("ck_pdf_manifest_items_page_start_positive")
        ),
        sa.CheckConstraint(
            "source_page_end >= source_page_start", name=op.f("ck_pdf_manifest_items_page_range")
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["pdf_import_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pdf_manifest_items")),
        sa.UniqueConstraint(
            "batch_id", "source_ordinal", name="uq_pdf_manifest_items_batch_ordinal"
        ),
    )
    op.create_index(op.f("ix_pdf_manifest_items_batch_id"), "pdf_manifest_items", ["batch_id"])


def downgrade() -> None:
    op.drop_table("pdf_manifest_items")
    op.drop_column("pdf_import_batches", "parsed_at")
    op.drop_column("pdf_import_batches", "parse_quality_count")
    op.drop_column("pdf_import_batches", "parsed_item_count")

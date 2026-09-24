"""Add private PDF source, import batch, lifecycle event, and review metadata.

Revision ID: 20260923_0005
Revises: 20260917_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260923_0005"
down_revision: str | None = "20260917_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATES = (
    "'uploaded', 'quarantined', 'parsing', 'parsed', 'reconciling', "
    "'needs_review', 'approved', 'rejected', 'failed', 'superseded'"
)


def upgrade() -> None:
    op.create_table(
        "pdf_source_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("storage_object_key", sa.String(500), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "byte_size > 0", name=op.f("ck_pdf_source_documents_byte_size_positive")
        ),
        sa.CheckConstraint(
            "page_count > 0", name=op.f("ck_pdf_source_documents_page_count_positive")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pdf_source_documents")),
        sa.UniqueConstraint("source_sha256", name=op.f("uq_pdf_source_documents_source_sha256")),
        sa.UniqueConstraint(
            "storage_object_key", name=op.f("uq_pdf_source_documents_storage_object_key")
        ),
    )
    op.create_table(
        "pdf_import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("parser_version", sa.String(80)),
        sa.Column("layout_version", sa.String(80)),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True)),
        sa.Column("rejection_code", sa.String(100)),
        sa.Column("superseded_by_batch_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            f"state IN ({_STATES})", name=op.f("ck_pdf_import_batches_state_values")
        ),
        sa.CheckConstraint(
            "period_end >= period_start", name=op.f("ck_pdf_import_batches_period_range")
        ),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["pdf_source_documents.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_batch_id"], ["pdf_import_batches.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pdf_import_batches")),
        sa.UniqueConstraint(
            "source_document_id", name=op.f("uq_pdf_import_batches_source_document_id")
        ),
    )
    op.create_index(op.f("ix_pdf_import_batches_partner_id"), "pdf_import_batches", ["partner_id"])
    op.create_index(
        op.f("ix_pdf_import_batches_uploaded_by"), "pdf_import_batches", ["uploaded_by"]
    )
    op.create_table(
        "pdf_import_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("from_state", sa.String(30)),
        sa.Column("to_state", sa.String(30), nullable=False),
        sa.Column("reason_code", sa.String(100)),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            f"from_state IS NULL OR from_state IN ({_STATES})",
            name=op.f("ck_pdf_import_events_from_state_values"),
        ),
        sa.CheckConstraint(
            f"to_state IN ({_STATES})", name=op.f("ck_pdf_import_events_to_state_values")
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["batch_id"], ["pdf_import_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pdf_import_events")),
    )
    op.create_index(
        op.f("ix_pdf_import_events_actor_user_id"),
        "pdf_import_events",
        ["actor_user_id"],
    )
    op.create_index(op.f("ix_pdf_import_events_batch_id"), "pdf_import_events", ["batch_id"])
    op.create_index(op.f("ix_pdf_import_events_occurred_at"), "pdf_import_events", ["occurred_at"])
    op.create_table(
        "pdf_import_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "decision IN ('approved', 'rejected', 'returned')",
            name=op.f("ck_pdf_import_reviews_decision_values"),
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["pdf_import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pdf_import_reviews")),
    )
    op.create_index(op.f("ix_pdf_import_reviews_batch_id"), "pdf_import_reviews", ["batch_id"])
    op.create_index(
        op.f("ix_pdf_import_reviews_reviewer_user_id"),
        "pdf_import_reviews",
        ["reviewer_user_id"],
    )


def downgrade() -> None:
    op.drop_table("pdf_import_reviews")
    op.drop_table("pdf_import_events")
    op.drop_table("pdf_import_batches")
    op.drop_table("pdf_source_documents")

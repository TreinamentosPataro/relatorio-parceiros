"""Auditable PDF-4 review decisions and optimistic revision.

Revision ID: 20260925_0009
Revises: 20260925_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260925_0009"
down_revision: str | None = "20260925_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("uq_partner_case_links_partner_entity_start"), "partner_case_links", type_="unique"
    )
    op.create_index(
        "uq_partner_case_links_active_entity_start",
        "partner_case_links",
        ["partner_id", "advbox_entity_type", "advbox_entity_id", "valid_from"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.add_column(
        "pdf_import_batches",
        sa.Column("review_revision", sa.Integer(), server_default="0", nullable=False),
    )
    op.drop_constraint(
        op.f("ck_pdf_import_reviews_decision_values"), "pdf_import_reviews", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_pdf_import_reviews_decision_values"),
        "pdf_import_reviews",
        "decision IN ('approved', 'rejected', 'returned', 'corrected', "
        "'reprocess_requested', 'superseded')",
    )
    op.add_column("pdf_import_reviews", sa.Column("reconciliation_item_id", sa.Uuid()))
    op.add_column("pdf_import_reviews", sa.Column("replacement_batch_id", sa.Uuid()))
    op.add_column("pdf_import_reviews", sa.Column("method", sa.String(length=40)))
    op.add_column("pdf_import_reviews", sa.Column("before_advbox_id", sa.BigInteger()))
    op.add_column("pdf_import_reviews", sa.Column("after_advbox_id", sa.BigInteger()))
    op.add_column(
        "pdf_import_reviews",
        sa.Column("review_revision", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_foreign_key(
        op.f("fk_pdf_import_reviews_reconciliation_item"),
        "pdf_import_reviews",
        "pdf_reconciliation_items",
        ["reconciliation_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_pdf_import_reviews_replacement_batch"),
        "pdf_import_reviews",
        "pdf_import_batches",
        ["replacement_batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_index("uq_partner_case_links_active_entity_start", table_name="partner_case_links")
    op.create_unique_constraint(
        "uq_partner_case_links_partner_entity_start",
        "partner_case_links",
        ["partner_id", "advbox_entity_type", "advbox_entity_id", "valid_from"],
    )
    op.drop_constraint(
        op.f("fk_pdf_import_reviews_replacement_batch"), "pdf_import_reviews", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_pdf_import_reviews_reconciliation_item"), "pdf_import_reviews", type_="foreignkey"
    )
    for name in (
        "review_revision",
        "after_advbox_id",
        "before_advbox_id",
        "method",
        "replacement_batch_id",
        "reconciliation_item_id",
    ):
        op.drop_column("pdf_import_reviews", name)
    op.drop_constraint(
        op.f("ck_pdf_import_reviews_decision_values"), "pdf_import_reviews", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_pdf_import_reviews_decision_values"),
        "pdf_import_reviews",
        "decision IN ('approved', 'rejected', 'returned')",
    )
    op.drop_column("pdf_import_batches", "review_revision")

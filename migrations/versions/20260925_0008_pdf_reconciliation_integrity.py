"""Bind local lawsuit ID to Advbox ID and preserve PDF reviewer provenance.

Revision ID: 20260925_0008
Revises: 20260925_0007
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260925_0008"
down_revision: str | None = "20260925_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("fk_pdf_reconciliation_items_matched_lawsuit_id_lawsuits"),
        "pdf_reconciliation_items",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_pdf_reconciliation_items_lawsuit_external",
        "pdf_reconciliation_items",
        "lawsuits",
        ["matched_lawsuit_id", "matched_advbox_id"],
        ["id", "advbox_id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        op.f("fk_partner_case_links_reviewed_by_users"),
        "partner_case_links",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_partner_case_links_reviewed_by_users"),
        "partner_case_links",
        "users",
        ["reviewed_by"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_partner_case_links_reviewed_by_users"),
        "partner_case_links",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_partner_case_links_reviewed_by_users"),
        "partner_case_links",
        "users",
        ["reviewed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(
        "fk_pdf_reconciliation_items_lawsuit_external",
        "pdf_reconciliation_items",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_pdf_reconciliation_items_matched_lawsuit_id_lawsuits"),
        "pdf_reconciliation_items",
        "lawsuits",
        ["matched_lawsuit_id"],
        ["id"],
        ondelete="RESTRICT",
    )

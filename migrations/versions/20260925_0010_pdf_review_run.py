"""Bind reprocessing requests to the exact reconciliation run.

Revision ID: 20260925_0010
Revises: 20260925_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260925_0010"
down_revision: str | None = "20260925_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pdf_import_reviews", sa.Column("reconciliation_run_id", sa.Uuid()))
    op.create_foreign_key(
        op.f("fk_pdf_import_reviews_reconciliation_run_id_pdf_reconciliation_runs"),
        "pdf_import_reviews",
        "pdf_reconciliation_runs",
        ["reconciliation_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_pdf_import_reviews_reconciliation_run_id_pdf_reconciliation_runs"),
        "pdf_import_reviews",
        type_="foreignkey",
    )
    op.drop_column("pdf_import_reviews", "reconciliation_run_id")

"""Bind synthetic report requests and versions to an approved PDF batch.

Revision ID: 20260925_0011
Revises: 20260925_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260925_0011"
down_revision: str | None = "20260925_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("report_versions", "report_generation_requests"):
        op.add_column(table, sa.Column("pdf_batch_id", sa.Uuid()))
        op.create_index(op.f(f"ix_{table}_pdf_batch_id"), table, ["pdf_batch_id"])
        op.create_foreign_key(
            op.f(f"fk_{table}_pdf_batch_id_pdf_import_batches"),
            table,
            "pdf_import_batches",
            ["pdf_batch_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index(
        "uq_report_versions_pdf_revision",
        "report_versions",
        ["partner_id", "source_digest"],
        unique=True,
        postgresql_where=sa.text("pdf_batch_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_report_versions_pdf_revision", table_name="report_versions")
    for table in ("report_generation_requests", "report_versions"):
        op.drop_constraint(
            op.f(f"fk_{table}_pdf_batch_id_pdf_import_batches"), table, type_="foreignkey"
        )
        op.drop_index(op.f(f"ix_{table}_pdf_batch_id"), table_name=table)
        op.drop_column(table, "pdf_batch_id")

"""Track physical removal of private source and report objects.

Revision ID: 20260925_0012
Revises: 20260925_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260925_0012"
down_revision: str | None = "20260925_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pdf_source_documents", sa.Column("purged_at", sa.DateTime(timezone=True)))
    op.add_column("report_versions", sa.Column("purged_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("report_versions", "purged_at")
    op.drop_column("pdf_source_documents", "purged_at")

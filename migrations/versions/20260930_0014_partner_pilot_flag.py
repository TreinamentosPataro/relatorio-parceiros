"""Admit real partners to the private pilot by an audited per-partner flag.

Revision ID: 20260930_0014
Revises: 20260930_0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260930_0014"
down_revision: str | None = "20260930_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "partners",
        sa.Column("pilot_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("partners", "pilot_enabled")

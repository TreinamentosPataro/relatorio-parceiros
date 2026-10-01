"""Store the report fields released by ADR-007 and the partnership percentage.

Revision ID: 20261001_0015
Revises: 20260930_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261001_0015"
down_revision: str | None = "20260930_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lawsuits", sa.Column("lawsuit_type_label", sa.String(250)))
    op.add_column("lawsuits", sa.Column("stage_label", sa.String(250)))
    op.add_column("lawsuits", sa.Column("step_label", sa.String(120)))
    op.add_column("lawsuits", sa.Column("responsible_name", sa.String(250)))
    op.add_column("lawsuits", sa.Column("contingency", sa.String(80)))
    op.add_column("lawsuits", sa.Column("fees_expected", sa.Numeric(18, 2)))
    op.add_column("transactions", sa.Column("description", sa.String(250)))
    op.add_column(
        "partners",
        sa.Column(
            "partnership_percentage",
            sa.Numeric(5, 2),
            server_default=sa.text("10.00"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_partners_partnership_percentage_range"),
        "partners",
        "partnership_percentage >= 0 AND partnership_percentage <= 100",
    )
    op.add_column("report_versions", sa.Column("partnership_percentage", sa.Numeric(5, 2)))


def downgrade() -> None:
    op.drop_column("report_versions", "partnership_percentage")
    op.drop_constraint(op.f("ck_partners_partnership_percentage_range"), "partners", type_="check")
    op.drop_column("partners", "partnership_percentage")
    op.drop_column("transactions", "description")
    for column in (
        "fees_expected",
        "contingency",
        "responsible_name",
        "step_label",
        "stage_label",
        "lawsuit_type_label",
    ):
        op.drop_column("lawsuits", column)

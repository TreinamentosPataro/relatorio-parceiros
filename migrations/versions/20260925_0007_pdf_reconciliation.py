"""Add versioned PDF reconciliation results and approved-link provenance.

Revision ID: 20260925_0007
Revises: 20260925_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260925_0007"
down_revision: str | None = "20260925_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pdf_reconciliation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parser_version", sa.String(80), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("snapshot_total", sa.Integer(), nullable=False),
        sa.Column("snapshot_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_total", sa.Integer(), nullable=False),
        sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("unmatched_count", sa.Integer(), nullable=False),
        sa.Column("ambiguous_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_source_count", sa.Integer(), nullable=False),
        sa.Column("invalid_identifier_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "snapshot_total >= 0",
            name=op.f("ck_pdf_reconciliation_runs_snapshot_total_nonnegative"),
        ),
        sa.CheckConstraint(
            "result_total >= 0", name=op.f("ck_pdf_reconciliation_runs_result_total_nonnegative")
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["pdf_import_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pdf_reconciliation_runs")),
        sa.UniqueConstraint(
            "batch_id",
            "snapshot_sha256",
            "parser_version",
            name="uq_pdf_reconciliation_runs_batch_snapshot_parser",
        ),
    )
    op.create_index(
        op.f("ix_pdf_reconciliation_runs_batch_id"), "pdf_reconciliation_runs", ["batch_id"]
    )
    op.create_table(
        "pdf_reconciliation_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manifest_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("method", sa.String(40)),
        sa.Column("reason_code", sa.String(80)),
        sa.Column("matched_advbox_id", sa.BigInteger()),
        sa.Column("matched_lawsuit_id", postgresql.UUID(as_uuid=True)),
        sa.Column("evidence_sha256", sa.String(64)),
        sa.Column("proposed_valid_from", sa.Date()),
        sa.Column("proposed_valid_to", sa.Date()),
        sa.CheckConstraint(
            "status IN ('matched', 'unmatched', 'ambiguous', "
            "'duplicate_source', 'invalid_identifier')",
            name=op.f("ck_pdf_reconciliation_items_status_values"),
        ),
        sa.CheckConstraint(
            "method IS NULL OR method IN ('process_number_exact', 'folder_exact_unique')",
            name=op.f("ck_pdf_reconciliation_items_method_values"),
        ),
        sa.CheckConstraint(
            "(status = 'matched' AND method IS NOT NULL AND matched_advbox_id IS NOT NULL "
            "AND evidence_sha256 IS NOT NULL AND proposed_valid_from IS NOT NULL "
            "AND proposed_valid_to IS NOT NULL) OR "
            "(status <> 'matched' AND method IS NULL AND matched_advbox_id IS NULL "
            "AND matched_lawsuit_id IS NULL AND evidence_sha256 IS NULL "
            "AND proposed_valid_from IS NULL AND proposed_valid_to IS NULL)",
            name=op.f("ck_pdf_reconciliation_items_matched_proposal_only"),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["pdf_reconciliation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["manifest_item_id"], ["pdf_manifest_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["matched_lawsuit_id"], ["lawsuits.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pdf_reconciliation_items")),
        sa.UniqueConstraint(
            "run_id", "manifest_item_id", name="uq_pdf_reconciliation_items_run_manifest"
        ),
    )
    op.create_index(
        op.f("ix_pdf_reconciliation_items_run_id"), "pdf_reconciliation_items", ["run_id"]
    )
    op.create_index(
        op.f("ix_pdf_reconciliation_items_manifest_item_id"),
        "pdf_reconciliation_items",
        ["manifest_item_id"],
    )

    op.add_column("partner_case_links", sa.Column("pdf_batch_id", postgresql.UUID(as_uuid=True)))
    op.add_column(
        "partner_case_links", sa.Column("pdf_reconciliation_item_id", postgresql.UUID(as_uuid=True))
    )
    op.add_column("partner_case_links", sa.Column("match_method", sa.String(40)))
    op.add_column("partner_case_links", sa.Column("evidence_sha256", sa.String(64)))
    op.add_column("partner_case_links", sa.Column("reviewed_by", postgresql.UUID(as_uuid=True)))
    op.add_column("partner_case_links", sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        op.f("fk_partner_case_links_pdf_batch_id_pdf_import_batches"),
        "partner_case_links",
        "pdf_import_batches",
        ["pdf_batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_partner_case_links_pdf_reconciliation_item_id_pdf_reconciliation_items"),
        "partner_case_links",
        "pdf_reconciliation_items",
        ["pdf_reconciliation_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_partner_case_links_reviewed_by_users"),
        "partner_case_links",
        "users",
        ["reviewed_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_partner_case_links_pdf_batch_id"), "partner_case_links", ["pdf_batch_id"]
    )
    op.create_unique_constraint(
        op.f("uq_partner_case_links_pdf_reconciliation_item_id"),
        "partner_case_links",
        ["pdf_reconciliation_item_id"],
    )
    op.drop_constraint(
        op.f("ck_partner_case_links_source_values"), "partner_case_links", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_partner_case_links_source_values"),
        "partner_case_links",
        "source IN ('manual_csv', 'admin', 'advbox_official', 'pdf_manifest')",
    )
    op.create_check_constraint(
        op.f("ck_partner_case_links_pdf_provenance_required"),
        "partner_case_links",
        "source <> 'pdf_manifest' OR (advbox_entity_type = 'lawsuit' AND pdf_batch_id IS NOT NULL "
        "AND pdf_reconciliation_item_id IS NOT NULL AND match_method IS NOT NULL "
        "AND evidence_sha256 IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_partner_case_links_pdf_review_required_for_active"),
        "partner_case_links",
        "source <> 'pdf_manifest' OR status <> 'active' OR "
        "(reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_partner_case_links_pdf_review_required_for_active"),
        "partner_case_links",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_partner_case_links_pdf_provenance_required"), "partner_case_links", type_="check"
    )
    op.drop_constraint(
        op.f("ck_partner_case_links_source_values"), "partner_case_links", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_partner_case_links_source_values"),
        "partner_case_links",
        "source IN ('manual_csv', 'admin', 'advbox_official')",
    )
    op.drop_constraint(
        op.f("uq_partner_case_links_pdf_reconciliation_item_id"),
        "partner_case_links",
        type_="unique",
    )
    op.drop_index(op.f("ix_partner_case_links_pdf_batch_id"), table_name="partner_case_links")
    op.drop_constraint(
        op.f("fk_partner_case_links_reviewed_by_users"), "partner_case_links", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_partner_case_links_pdf_reconciliation_item_id_pdf_reconciliation_items"),
        "partner_case_links",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_partner_case_links_pdf_batch_id_pdf_import_batches"),
        "partner_case_links",
        type_="foreignkey",
    )
    for column in (
        "reviewed_at",
        "reviewed_by",
        "evidence_sha256",
        "match_method",
        "pdf_reconciliation_item_id",
        "pdf_batch_id",
    ):
        op.drop_column("partner_case_links", column)
    op.drop_table("pdf_reconciliation_items")
    op.drop_table("pdf_reconciliation_runs")

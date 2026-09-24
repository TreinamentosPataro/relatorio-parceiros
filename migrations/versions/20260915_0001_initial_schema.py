"""Create the normalized partner reporting schema.

Revision ID: 20260915_0001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260915_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column[object]:
    return sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False)


def _created_updated() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "partners",
        _uuid_pk(),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_created_updated(),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'pending')",
            name=op.f("ck_partners_status_values"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partners")),
        sa.UniqueConstraint("external_id", name=op.f("uq_partners_external_id")),
    )

    op.create_table(
        "customers",
        _uuid_pk(),
        sa.Column("advbox_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=True),
        sa.Column("identification", sa.String(length=100), nullable=True),
        sa.Column("origin", sa.String(length=250), nullable=True),
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_created_updated(),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'deleted')",
            name=op.f("ck_customers_status_values"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("advbox_id", name=op.f("uq_customers_advbox_id")),
        sa.UniqueConstraint("id", "advbox_id", name="uq_customers_id_advbox_id"),
    )

    op.create_table(
        "lawsuits",
        _uuid_pk(),
        sa.Column("advbox_id", sa.BigInteger(), nullable=False),
        sa.Column("process_number", sa.String(length=100), nullable=True),
        sa.Column("protocol_number", sa.String(length=100), nullable=True),
        sa.Column("folder", sa.String(length=250), nullable=True),
        sa.Column("group_id", sa.BigInteger(), nullable=True),
        sa.Column("lawsuit_type_id", sa.BigInteger(), nullable=True),
        sa.Column("stage_id", sa.BigInteger(), nullable=True),
        sa.Column("responsible_id", sa.BigInteger(), nullable=True),
        sa.Column("process_date", sa.Date(), nullable=True),
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_created_updated(),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'deleted')",
            name=op.f("ck_lawsuits_status_values"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lawsuits")),
        sa.UniqueConstraint("advbox_id", name=op.f("uq_lawsuits_advbox_id")),
        sa.UniqueConstraint("id", "advbox_id", name="uq_lawsuits_id_advbox_id"),
    )
    op.create_index(op.f("ix_lawsuits_process_number"), "lawsuits", ["process_number"])
    op.create_index(op.f("ix_lawsuits_protocol_number"), "lawsuits", ["protocol_number"])
    op.create_index(op.f("ix_lawsuits_folder"), "lawsuits", ["folder"])

    op.create_table(
        "users",
        _uuid_pk(),
        sa.Column("external_subject", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=250), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        *_created_updated(),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'pending')",
            name=op.f("ck_users_status_values"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("external_subject", name=op.f("uq_users_external_subject")),
    )

    op.create_table(
        "roles",
        _uuid_pk(),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=250), nullable=True),
        *_created_updated(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("key", name=op.f("uq_roles_key")),
    )

    op.create_table(
        "sync_runs",
        _uuid_pk(),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_offset", sa.BigInteger(), nullable=True),
        sa.Column("fetched_count", sa.Integer(), nullable=False),
        sa.Column("inserted_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'partial')",
            name=op.f("ck_sync_runs_status_values"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_runs")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_sync_runs_idempotency_key")),
    )
    op.create_index(op.f("ix_sync_runs_resource_type"), "sync_runs", ["resource_type"])

    op.create_table(
        "lawsuit_customers",
        _uuid_pk(),
        sa.Column("lawsuit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        *_created_updated(),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_lawsuit_customers_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lawsuit_id"],
            ["lawsuits.id"],
            name=op.f("fk_lawsuit_customers_lawsuit_id_lawsuits"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lawsuit_customers")),
        sa.UniqueConstraint(
            "lawsuit_id", "customer_id", name="uq_lawsuit_customers_lawsuit_customer"
        ),
    )
    op.create_index(op.f("ix_lawsuit_customers_customer_id"), "lawsuit_customers", ["customer_id"])
    op.create_index(op.f("ix_lawsuit_customers_lawsuit_id"), "lawsuit_customers", ["lawsuit_id"])

    op.create_table(
        "user_roles",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        *_created_updated(),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_roles")),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
    )
    op.create_index(op.f("ix_user_roles_role_id"), "user_roles", ["role_id"])
    op.create_index(op.f("ix_user_roles_user_id"), "user_roles", ["user_id"])

    op.create_table(
        "partner_case_links",
        _uuid_pk(),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("advbox_entity_type", sa.String(length=20), nullable=False),
        sa.Column("advbox_entity_id", sa.BigInteger(), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lawsuit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        *_created_updated(),
        sa.CheckConstraint(
            "advbox_entity_type IN ('customer', 'lawsuit')",
            name=op.f("ck_partner_case_links_entity_type_values"),
        ),
        sa.CheckConstraint(
            "(advbox_entity_type = 'customer' AND customer_id IS NOT NULL "
            "AND lawsuit_id IS NULL) OR "
            "(advbox_entity_type = 'lawsuit' AND lawsuit_id IS NOT NULL AND customer_id IS NULL)",
            name=op.f("ck_partner_case_links_target_matches_type"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'pending')",
            name=op.f("ck_partner_case_links_status_values"),
        ),
        sa.CheckConstraint(
            "source IN ('manual_csv', 'admin', 'advbox_official')",
            name=op.f("ck_partner_case_links_source_values"),
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name=op.f("ck_partner_case_links_valid_date_range"),
        ),
        postgresql.ExcludeConstraint(
            ("advbox_entity_type", "="),
            ("advbox_entity_id", "="),
            (
                sa.text("daterange(valid_from, COALESCE(valid_to, 'infinity'::date), '[]')"),
                "&&",
            ),
            where=sa.text("status = 'active'"),
            using="gist",
            name="ex_partner_case_links_no_active_overlap",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["customer_id", "advbox_entity_id"],
            ["customers.id", "customers.advbox_id"],
            name="fk_partner_case_links_customer_external",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["lawsuit_id", "advbox_entity_id"],
            ["lawsuits.id", "lawsuits.advbox_id"],
            name="fk_partner_case_links_lawsuit_external",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partner_case_links")),
        sa.UniqueConstraint(
            "partner_id",
            "advbox_entity_type",
            "advbox_entity_id",
            "valid_from",
            name="uq_partner_case_links_partner_entity_start",
        ),
    )
    op.create_index(
        op.f("ix_partner_case_links_customer_id"), "partner_case_links", ["customer_id"]
    )
    op.create_index(op.f("ix_partner_case_links_lawsuit_id"), "partner_case_links", ["lawsuit_id"])
    op.create_index(op.f("ix_partner_case_links_partner_id"), "partner_case_links", ["partner_id"])
    op.create_index(
        "ix_partner_case_links_entity_period",
        "partner_case_links",
        ["advbox_entity_type", "advbox_entity_id", "valid_from", "valid_to"],
    )

    op.create_table(
        "movements",
        _uuid_pk(),
        sa.Column("lawsuit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *_created_updated(),
        sa.ForeignKeyConstraint(["lawsuit_id"], ["lawsuits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_movements")),
        sa.UniqueConstraint(
            "lawsuit_id",
            "source_fingerprint",
            name="uq_movements_lawsuit_fingerprint",
        ),
    )
    op.create_index(op.f("ix_movements_lawsuit_id"), "movements", ["lawsuit_id"])

    op.create_table(
        "transactions",
        _uuid_pk(),
        sa.Column("advbox_id", sa.BigInteger(), nullable=False),
        sa.Column("lawsuit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("amount_status", sa.String(length=30), nullable=False),
        sa.Column("entry_type", sa.String(length=40), nullable=True),
        sa.Column("category", sa.String(length=250), nullable=True),
        sa.Column("cost_center", sa.String(length=250), nullable=True),
        sa.Column("competence", sa.String(length=40), nullable=True),
        sa.Column("date_due", sa.Date(), nullable=True),
        sa.Column("date_payment", sa.Date(), nullable=True),
        sa.Column("is_internal", sa.Boolean(), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        *_created_updated(),
        sa.CheckConstraint(
            "amount_status IN ('available', 'not_provided', 'not_applicable', "
            "'pending_validation', 'restricted')",
            name=op.f("ck_transactions_amount_status_values"),
        ),
        sa.CheckConstraint(
            "(amount_status = 'available' AND amount IS NOT NULL) OR "
            "(amount_status <> 'available' AND amount IS NULL)",
            name=op.f("ck_transactions_amount_matches_status"),
        ),
        sa.ForeignKeyConstraint(["lawsuit_id"], ["lawsuits.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
        sa.UniqueConstraint("advbox_id", name=op.f("uq_transactions_advbox_id")),
    )
    op.create_index(op.f("ix_transactions_lawsuit_id"), "transactions", ["lawsuit_id"])

    op.create_table(
        "sync_errors",
        _uuid_pk(),
        sa.Column("sync_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=False),
        sa.Column("http_status", sa.SmallInteger(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("external_reference_hash", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["sync_run_id"], ["sync_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_errors")),
    )
    op.create_index(op.f("ix_sync_errors_error_code"), "sync_errors", ["error_code"])
    op.create_index(op.f("ix_sync_errors_sync_run_id"), "sync_errors", ["sync_run_id"])

    op.create_table(
        "report_versions",
        _uuid_pk(),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("storage_object_key", sa.String(length=500), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'validated', 'published', 'superseded', 'failed')",
            name=op.f("ck_report_versions_status_values"),
        ),
        sa.CheckConstraint(
            "period_end >= period_start",
            name=op.f("ck_report_versions_period_range"),
        ),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_versions")),
        sa.UniqueConstraint(
            "partner_id",
            "period_start",
            "period_end",
            "version",
            name="uq_report_versions_partner_period_version",
        ),
    )
    op.create_index(op.f("ix_report_versions_partner_id"), "report_versions", ["partner_id"])

    op.create_table(
        "partner_financial_agreements",
        _uuid_pk(),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lawsuit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revenue_type", sa.String(length=80), nullable=False),
        sa.Column("percentage", sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column("deduction_fixed_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("deduction_percentage", sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column("rounding_mode", sa.String(length=20), nullable=False),
        sa.Column("rounding_scale", sa.SmallInteger(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        *_created_updated(),
        sa.CheckConstraint(
            "percentage >= 0 AND percentage <= 100",
            name=op.f("ck_partner_financial_agreements_percentage_range"),
        ),
        sa.CheckConstraint(
            "deduction_percentage >= 0 AND deduction_percentage <= 100",
            name=op.f("ck_partner_financial_agreements_deduction_percentage_range"),
        ),
        sa.CheckConstraint(
            "deduction_fixed_amount >= 0",
            name=op.f("ck_partner_financial_agreements_deduction_amount_nonnegative"),
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name=op.f("ck_partner_financial_agreements_valid_date_range"),
        ),
        sa.CheckConstraint(
            "rounding_mode IN ('half_up', 'half_even', 'down', 'up')",
            name=op.f("ck_partner_financial_agreements_rounding_mode_values"),
        ),
        sa.CheckConstraint(
            "rounding_scale >= 0 AND rounding_scale <= 4",
            name=op.f("ck_partner_financial_agreements_rounding_scale"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'pending')",
            name=op.f("ck_partner_financial_agreements_status_values"),
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lawsuit_id"], ["lawsuits.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partner_financial_agreements")),
        sa.UniqueConstraint(
            "partner_id",
            "lawsuit_id",
            "revenue_type",
            "valid_from",
            name="uq_partner_financial_agreements_partner_lawsuit_revenue_start",
        ),
    )
    op.create_index(
        op.f("ix_partner_financial_agreements_lawsuit_id"),
        "partner_financial_agreements",
        ["lawsuit_id"],
    )
    op.create_index(
        op.f("ix_partner_financial_agreements_partner_id"),
        "partner_financial_agreements",
        ["partner_id"],
    )

    op.create_table(
        "section_statuses",
        _uuid_pk(),
        sa.Column("report_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_key", sa.String(length=100), nullable=False),
        sa.Column("availability_status", sa.String(length=30), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "availability_status IN ('available', 'not_provided', 'not_applicable', "
            "'pending_validation', 'restricted')",
            name=op.f("ck_section_statuses_availability_status_values"),
        ),
        sa.ForeignKeyConstraint(["report_version_id"], ["report_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_section_statuses")),
        sa.UniqueConstraint(
            "report_version_id",
            "section_key",
            name="uq_section_statuses_report_section",
        ),
    )
    op.create_index(
        op.f("ix_section_statuses_report_version_id"),
        "section_statuses",
        ["report_version_id"],
    )

    op.create_table(
        "audit_events",
        _uuid_pk(),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("changed_fields", postgresql.ARRAY(sa.String(length=100)), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_action"), "audit_events", ["action"])
    op.create_index(op.f("ix_audit_events_actor_user_id"), "audit_events", ["actor_user_id"])
    op.create_index(op.f("ix_audit_events_correlation_id"), "audit_events", ["correlation_id"])
    op.create_index(op.f("ix_audit_events_occurred_at"), "audit_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("section_statuses")
    op.drop_table("partner_financial_agreements")
    op.drop_table("report_versions")
    op.drop_table("sync_errors")
    op.drop_table("transactions")
    op.drop_table("movements")
    op.drop_table("partner_case_links")
    op.drop_table("user_roles")
    op.drop_table("lawsuit_customers")
    op.drop_table("sync_runs")
    op.drop_table("roles")
    op.drop_table("users")
    op.drop_table("lawsuits")
    op.drop_table("customers")
    op.drop_table("partners")

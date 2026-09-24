"""Normalized relational model for synchronization, linkage, and reports."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from partner_reports.persistence.base import Base, TimestampMixin, UuidPrimaryKeyMixin

AVAILABILITY_VALUES = (
    "'available', 'not_provided', 'not_applicable', 'pending_validation', 'restricted'"
)
ACTIVE_STATUS_VALUES = "'active', 'inactive', 'pending'"


class Partner(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "partners"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({ACTIVE_STATUS_VALUES})",
            name="status_values",
        ),
    )

    external_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Customer(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive', 'deleted')",
            name="status_values",
        ),
        UniqueConstraint("id", "advbox_id", name="uq_customers_id_advbox_id"),
    )

    advbox_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(250))
    identification: Mapped[str | None] = mapped_column(String(100))
    origin: Mapped[str | None] = mapped_column(String(250))
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report_hash: Mapped[str | None] = mapped_column(String(64))
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Lawsuit(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lawsuits"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive', 'deleted')",
            name="status_values",
        ),
        UniqueConstraint("id", "advbox_id", name="uq_lawsuits_id_advbox_id"),
    )

    advbox_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    process_number: Mapped[str | None] = mapped_column(String(100), index=True)
    protocol_number: Mapped[str | None] = mapped_column(String(100), index=True)
    folder: Mapped[str | None] = mapped_column(String(250), index=True)
    group_id: Mapped[int | None] = mapped_column(BigInteger)
    lawsuit_type_id: Mapped[int | None] = mapped_column(BigInteger)
    stage_id: Mapped[int | None] = mapped_column(BigInteger)
    responsible_id: Mapped[int | None] = mapped_column(BigInteger)
    process_date: Mapped[date | None] = mapped_column(Date)
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report_hash: Mapped[str | None] = mapped_column(String(64))
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LawsuitCustomer(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lawsuit_customers"
    __table_args__ = (
        UniqueConstraint("lawsuit_id", "customer_id", name="uq_lawsuit_customers_lawsuit_customer"),
    )

    lawsuit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("lawsuits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )


class AppUser(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({ACTIVE_STATUS_VALUES})",
            name="status_values",
        ),
    )

    external_subject: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(250))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PortalCredential(UuidPrimaryKeyMixin, Base):
    __tablename__ = "portal_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    login_name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)


class PortalSession(UuidPrimaryKeyMixin, Base):
    __tablename__ = "portal_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PortalLoginAttempt(UuidPrimaryKeyMixin, Base):
    __tablename__ = "portal_login_attempts"

    bucket_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Role(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(250))


class UserRole(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )


class PartnerCaseLink(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "partner_case_links"
    __table_args__ = (
        CheckConstraint(
            "advbox_entity_type IN ('customer', 'lawsuit')",
            name="entity_type_values",
        ),
        CheckConstraint(
            "(advbox_entity_type = 'customer' AND customer_id IS NOT NULL "
            "AND lawsuit_id IS NULL) OR "
            "(advbox_entity_type = 'lawsuit' AND lawsuit_id IS NOT NULL "
            "AND customer_id IS NULL)",
            name="target_matches_type",
        ),
        CheckConstraint(
            f"status IN ({ACTIVE_STATUS_VALUES})",
            name="status_values",
        ),
        CheckConstraint(
            "source IN ('manual_csv', 'admin', 'advbox_official')",
            name="source_values",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="valid_date_range",
        ),
        UniqueConstraint(
            "partner_id",
            "advbox_entity_type",
            "advbox_entity_id",
            "valid_from",
            name="uq_partner_case_links_partner_entity_start",
        ),
        Index(
            "ix_partner_case_links_entity_period",
            "advbox_entity_type",
            "advbox_entity_id",
            "valid_from",
            "valid_to",
        ),
        ForeignKeyConstraint(
            ["customer_id", "advbox_entity_id"],
            ["customers.id", "customers.advbox_id"],
            ondelete="RESTRICT",
            name="fk_partner_case_links_customer_external",
        ),
        ForeignKeyConstraint(
            ["lawsuit_id", "advbox_entity_id"],
            ["lawsuits.id", "lawsuits.advbox_id"],
            ondelete="RESTRICT",
            name="fk_partner_case_links_lawsuit_external",
        ),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    advbox_entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    advbox_entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    lawsuit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )


class Movement(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "movements"
    __table_args__ = (
        UniqueConstraint(
            "lawsuit_id",
            "source_fingerprint",
            name="uq_movements_lawsuit_fingerprint",
        ),
    )

    lawsuit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("lawsuits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FinancialTransaction(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint(
            f"amount_status IN ({AVAILABILITY_VALUES})",
            name="amount_status_values",
        ),
        CheckConstraint(
            "(amount_status = 'available' AND amount IS NOT NULL) OR "
            "(amount_status <> 'available' AND amount IS NULL)",
            name="amount_matches_status",
        ),
    )

    advbox_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    lawsuit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("lawsuits.id", ondelete="SET NULL"), index=True
    )
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    amount_status: Mapped[str] = mapped_column(String(30), nullable=False)
    entry_type: Mapped[str | None] = mapped_column(String(40))
    category: Mapped[str | None] = mapped_column(String(250))
    cost_center: Mapped[str | None] = mapped_column(String(250))
    competence: Mapped[str | None] = mapped_column(String(40))
    date_due: Mapped[date | None] = mapped_column(Date)
    date_payment: Mapped[date | None] = mapped_column(Date)
    is_internal: Mapped[bool | None] = mapped_column(Boolean)
    report_hash: Mapped[str | None] = mapped_column(String(64))
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SyncRun(UuidPrimaryKeyMixin, Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'partial')",
            name="status_values",
        ),
    )

    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_offset: Mapped[int | None] = mapped_column(BigInteger)
    expected_total: Mapped[int | None] = mapped_column(BigInteger)
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SyncError(UuidPrimaryKeyMixin, Base):
    __tablename__ = "sync_errors"

    sync_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    error_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    external_reference_hash: Mapped[str | None] = mapped_column(String(64))
    page_offset: Mapped[int | None] = mapped_column(BigInteger, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SyncChangedPartner(UuidPrimaryKeyMixin, Base):
    __tablename__ = "sync_changed_partners"
    __table_args__ = (
        UniqueConstraint("sync_run_id", "partner_id", name="uq_sync_changed_partners_run_partner"),
    )

    sync_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    partner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class ReportVersion(UuidPrimaryKeyMixin, Base):
    __tablename__ = "report_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'validated', 'published', 'superseded', 'failed')",
            name="status_values",
        ),
        UniqueConstraint(
            "partner_id",
            "period_start",
            "period_end",
            "version",
            name="uq_report_versions_partner_period_version",
        ),
        CheckConstraint("period_end >= period_start", name="period_range"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    storage_object_key: Mapped[str | None] = mapped_column(String(500))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    source_digest: Mapped[str | None] = mapped_column(String(64))
    customer_count: Mapped[int | None] = mapped_column(Integer)
    case_count: Mapped[int | None] = mapped_column(Integer)


class SyntheticPortfolio(UuidPrimaryKeyMixin, Base):
    """Development-only change source; never populated from the real API."""

    __tablename__ = "synthetic_portfolios"
    __table_args__ = (
        CheckConstraint("scenario IN ('zero', 'one', 'many')", name="scenario_values"),
        CheckConstraint("revision > 0", name="revision_positive"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    scenario: Mapped[str] = mapped_column(String(10), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ReportGenerationRequest(UuidPrimaryKeyMixin, Base):
    __tablename__ = "report_generation_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')", name="status_values"
        ),
        Index(
            "uq_report_generation_requests_active_partner",
            "partner_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    source_digest: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


PDF_IMPORT_STATES = (
    "'uploaded', 'quarantined', 'parsing', 'parsed', 'reconciling', "
    "'needs_review', 'approved', 'rejected', 'failed', 'superseded'"
)


class PdfSourceDocument(UuidPrimaryKeyMixin, Base):
    """Private source object metadata; the original client filename is never stored."""

    __tablename__ = "pdf_source_documents"
    __table_args__ = (
        CheckConstraint("byte_size > 0", name="byte_size_positive"),
        CheckConstraint("page_count > 0", name="page_count_positive"),
    )

    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    storage_object_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PdfImportBatch(UuidPrimaryKeyMixin, TimestampMixin, Base):
    """One selected partner and reporting period backed by a private PDF source."""

    __tablename__ = "pdf_import_batches"
    __table_args__ = (
        CheckConstraint(f"state IN ({PDF_IMPORT_STATES})", name="state_values"),
        CheckConstraint("period_end >= period_start", name="period_range"),
    )

    source_document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("pdf_source_documents.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    partner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    parser_version: Mapped[str | None] = mapped_column(String(80))
    layout_version: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    rejection_code: Mapped[str | None] = mapped_column(String(100))
    superseded_by_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("pdf_import_batches.id", ondelete="RESTRICT")
    )


class PdfImportEvent(UuidPrimaryKeyMixin, Base):
    """Append-only allowlisted state history for one import batch."""

    __tablename__ = "pdf_import_events"
    __table_args__ = (
        CheckConstraint(
            f"from_state IS NULL OR from_state IN ({PDF_IMPORT_STATES})",
            name="from_state_values",
        ),
        CheckConstraint(f"to_state IN ({PDF_IMPORT_STATES})", name="to_state_values"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("pdf_import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    from_state: Mapped[str | None] = mapped_column(String(30))
    to_state: Mapped[str] = mapped_column(String(30), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(100))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class PdfImportReview(UuidPrimaryKeyMixin, Base):
    """Reserved audit record for a future authorized human review decision."""

    __tablename__ = "pdf_import_reviews"
    __table_args__ = (
        CheckConstraint("decision IN ('approved', 'rejected', 'returned')", name="decision_values"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("pdf_import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SectionStatus(UuidPrimaryKeyMixin, Base):
    __tablename__ = "section_statuses"
    __table_args__ = (
        CheckConstraint(
            f"availability_status IN ({AVAILABILITY_VALUES})",
            name="availability_status_values",
        ),
        UniqueConstraint(
            "report_version_id",
            "section_key",
            name="uq_section_statuses_report_section",
        ),
    )

    report_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("report_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_key: Mapped[str] = mapped_column(String(100), nullable=False)
    availability_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(100))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PartnerFinancialAgreement(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "partner_financial_agreements"
    __table_args__ = (
        CheckConstraint("percentage >= 0 AND percentage <= 100", name="percentage_range"),
        CheckConstraint(
            "deduction_percentage >= 0 AND deduction_percentage <= 100",
            name="deduction_percentage_range",
        ),
        CheckConstraint("deduction_fixed_amount >= 0", name="deduction_amount_nonnegative"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="valid_date_range"),
        CheckConstraint(
            "rounding_mode IN ('half_up', 'half_even', 'down', 'up')",
            name="rounding_mode_values",
        ),
        CheckConstraint("rounding_scale >= 0 AND rounding_scale <= 4", name="rounding_scale"),
        CheckConstraint(
            f"status IN ({ACTIVE_STATUS_VALUES})",
            name="status_values",
        ),
        UniqueConstraint(
            "partner_id",
            "lawsuit_id",
            "revenue_type",
            "valid_from",
            name="uq_partner_financial_agreements_partner_lawsuit_revenue_start",
        ),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lawsuit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("lawsuits.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    revenue_type: Mapped[str] = mapped_column(String(80), nullable=False)
    percentage: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    deduction_fixed_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00")
    )
    deduction_percentage: Mapped[Decimal] = mapped_column(
        Numeric(7, 4), nullable=False, default=Decimal("0.0000")
    )
    rounding_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="half_up")
    rounding_scale: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=2)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )


class AuditEvent(UuidPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    changed_fields: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(100))

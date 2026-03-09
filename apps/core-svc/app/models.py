from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)


class Connection(Base, TimestampMixin):
    __tablename__ = "connections"
    __table_args__ = (UniqueConstraint("tenant_id", "connector", name="uq_tenant_connector"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    connector: Mapped[str] = mapped_column(String(50), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    credential_ref: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class CredentialVault(Base, TimestampMixin):
    __tablename__ = "credential_vault"
    __table_args__ = (
        Index("idx_credential_vault_tenant_connector", "tenant_id", "connector"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    connector: Mapped[str] = mapped_column(String(50), nullable=False)
    secret_type: Mapped[str] = mapped_column(String(50), default="api_token", nullable=False)
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[str] = mapped_column(String(20), default="v1", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class GmailOAuthAccount(Base, TimestampMixin):
    __tablename__ = "gmail_oauth_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "account_id", name="uq_tenant_gmail_account"),
        Index("idx_gmail_oauth_tenant", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    credential_ref: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)


class OAuthState(Base, TimestampMixin):
    __tablename__ = "oauth_states"
    __table_args__ = (
        UniqueConstraint("state", name="uq_oauth_state"),
        Index("idx_oauth_state_expiry", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    connector: Mapped[str] = mapped_column(String(50), nullable=False)
    state: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_json: Mapped[dict] = mapped_column("payload", JSON, default=dict, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CanonicalProduct(Base, TimestampMixin):
    __tablename__ = "canonical_products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)


class CanonicalVariant(Base, TimestampMixin):
    __tablename__ = "canonical_variants"
    __table_args__ = (UniqueConstraint("tenant_id", "sku", name="uq_tenant_sku"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_products.id", ondelete="CASCADE"), nullable=False
    )
    sku: Mapped[str] = mapped_column(String(120), nullable=False)
    barcode: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    option_values: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class StockLevel(Base, TimestampMixin):
    __tablename__ = "stock_levels"
    __table_args__ = (UniqueConstraint("tenant_id", "variant_id", "location", name="uq_stock_location"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    variant_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_variants.id", ondelete="CASCADE"), nullable=False
    )
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    available_to_sell: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_pushed_qty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CanonicalOrder(Base, TimestampMixin):
    __tablename__ = "canonical_orders"
    __table_args__ = (UniqueConstraint("tenant_id", "order_number", name="uq_tenant_order_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    order_number: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="new", nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    payload_json: Mapped[dict] = mapped_column("payload", JSON, default=dict, nullable=False)


class CanonicalEmail(Base, TimestampMixin):
    __tablename__ = "canonical_emails"
    __table_args__ = (Index("idx_canonical_emails_tenant_received", "tenant_id", "received_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    from_address: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    to_address: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="unknown", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="received", nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    payload_json: Mapped[dict] = mapped_column("payload", JSON, default=dict, nullable=False)


class ExternalEntityMap(Base, TimestampMixin):
    __tablename__ = "external_entity_map"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "connector",
            "entity_type",
            "external_id",
            name="uq_external_entity",
        ),
        Index("idx_internal_entity", "tenant_id", "entity_type", "internal_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    connector: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    internal_id: Mapped[str] = mapped_column(String(36), nullable=False)
    last_seen_hash: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    snapshot_json: Mapped[dict] = mapped_column("snapshot", JSON, default=dict, nullable=False)


class SyncJob(Base, TimestampMixin):
    __tablename__ = "sync_jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_job_idempotency"),
        Index("idx_job_status_next", "status", "next_run_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    connector: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    error_code: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    error_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    payload_json: Mapped[dict] = mapped_column("payload", JSON, default=dict, nullable=False)


class OutboxEvent(Base, TimestampMixin):
    __tablename__ = "outbox_events"
    __table_args__ = (Index("idx_outbox_published", "published_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    topic: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_json: Mapped[dict] = mapped_column("payload", JSON, default=dict, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WebhookEvent(Base, TimestampMixin):
    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "connector", "delivery_id", name="uq_webhook_delivery"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    connector: Mapped[str] = mapped_column(String(50), nullable=False)
    delivery_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_json: Mapped[dict] = mapped_column("payload", JSON, default=dict, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("idx_audit_logs_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    actor: Mapped[str] = mapped_column(String(120), default="ui-user", nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    details_json: Mapped[dict] = mapped_column("details", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

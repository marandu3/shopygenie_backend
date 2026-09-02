import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TenantScopedMixin, TimestampMixin, UUIDPKMixin
from app.models.organization import SubscriptionPlan


class ActivationRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ActivationRequest(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """A tenant's self-reported claim of having already paid for a package
    outside the system (bank transfer, mobile money, etc.), submitted with a
    reference number for the platform owner to manually verify and activate.
    No payment gateway is wired — verification is entirely human."""

    __tablename__ = "activation_requests"

    requested_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    plan_requested: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan, name="subscription_plan"), nullable=False
    )
    reference_number: Mapped[str] = mapped_column(String(100), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[ActivationRequestStatus] = mapped_column(
        Enum(ActivationRequestStatus, name="activation_request_status"),
        default=ActivationRequestStatus.PENDING,
        nullable=False,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class BillingPlanConfig(UUIDPKMixin, TimestampMixin, Base):
    """Platform-owner-editable catalog entry for one SubscriptionPlan code
    (MASTER PROMPT §61: "names, descriptions, prices, features, and quotas
    must be configurable by Platform Owners"). The enum code is the stable
    identifier organizations reference; everything else here is editable.
    Seeded with one row per SubscriptionPlan value — see scripts/seed.py."""

    __tablename__ = "billing_plan_configs"

    code: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan, name="subscription_plan"), nullable=False, unique=True
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    price_monthly: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="TZS", nullable=False)
    max_branches: Mapped[int | None] = mapped_column(nullable=True)
    max_workers: Mapped[int | None] = mapped_column(nullable=True)
    whatsapp_quota_monthly: Mapped[int | None] = mapped_column(nullable=True)
    storage_quota_mb: Mapped[int | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)


class SmsMessageType(str, enum.Enum):
    WORKER_INVITE = "WORKER_INVITE"
    SALE_RECEIPT = "SALE_RECEIPT"
    DEBT_REMINDER = "DEBT_REMINDER"
    TEST = "TEST"


class SmsMessageStatus(str, enum.Enum):
    SENT = "SENT"
    FAILED = "FAILED"


class SmsMessage(UUIDPKMixin, TenantScopedMixin, Base):
    """Outbound SMS log (MASTER PROMPT §45, §48) — every attempt through
    app/services/notifications.send_sms writes exactly one row here,
    success or failure, so Message History is always complete."""

    __tablename__ = "sms_messages"

    message_type: Mapped[SmsMessageType] = mapped_column(Enum(SmsMessageType, name="sms_message_type"), nullable=False)
    recipient: Mapped[str] = mapped_column(String(30), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[SmsMessageStatus] = mapped_column(Enum(SmsMessageStatus, name="sms_message_status"), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    related_sale_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales.id", ondelete="SET NULL"), nullable=True
    )
    sent_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

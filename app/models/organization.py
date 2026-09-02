import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class SubscriptionStatus(str, enum.Enum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    GRACE_PERIOD = "GRACE_PERIOD"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class SubscriptionPlan(str, enum.Enum):
    """MASTER PROMPT §61: Basic / Professional / Business / Enterprise. The
    code here is the stable identifier; display name/price/quotas for each
    are configurable by a platform owner via BillingPlanConfig, not fixed."""

    BASIC = "BASIC"
    PROFESSIONAL = "PROFESSIONAL"
    BUSINESS = "BUSINESS"
    ENTERPRISE = "ENTERPRISE"


class Organization(UUIDPKMixin, TimestampMixin, Base):
    """A tenant. Every business-owned row in the system ultimately traces back
    to exactly one Organization via organization_id."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)

    currency: Mapped[str] = mapped_column(String(3), default="TZS", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Africa/Dar_es_Salaam", nullable=False)
    tax_rate_percent: Mapped[float] = mapped_column(default=0, nullable=False)
    tax_inclusive_pricing: Mapped[bool] = mapped_column(default=False, nullable=False)

    low_stock_default_threshold: Mapped[int] = mapped_column(default=5, nullable=False)

    # Null = no restriction (every discount auto-approves) — preserves prior
    # behavior for tenants that never configure this. Set = a cashier's
    # discount above this percent of the sale's subtotal requires a
    # DISCOUNTS_APPROVE-holding approver's id on the sale payload.
    discount_auto_approve_threshold_percent: Mapped[float | None] = mapped_column(nullable=True)

    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"), default=SubscriptionStatus.TRIAL, nullable=False
    )
    subscription_plan: Mapped[SubscriptionPlan | None] = mapped_column(
        Enum(SubscriptionPlan, name="subscription_plan"), nullable=True
    )
    subscription_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # --- Tenant SMSGate configuration (MASTER PROMPT §43) ---
    # Deliberately per-organization, never a shared/global credential. The
    # API key is encrypted at rest (app/core/crypto.py) and never returned
    # in plaintext by any endpoint.
    sms_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    sms_base_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sms_api_key_encrypted: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sms_sender_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sms_last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sms_last_test_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sms_last_test_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    branches: Mapped[list["Branch"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class Branch(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "branches"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="branches")
    registers: Mapped[list["Register"]] = relationship(back_populates="branch", cascade="all, delete-orphan")


class Register(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "registers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    branch: Mapped["Branch"] = relationship(back_populates="registers")

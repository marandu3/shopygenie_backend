import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Uuid
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

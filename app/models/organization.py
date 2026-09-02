import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Uuid
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

    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"), default=SubscriptionStatus.TRIAL, nullable=False
    )

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

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

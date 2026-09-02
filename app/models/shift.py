import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TenantScopedMixin, UUIDPKMixin


class ShiftStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class CashMovementType(str, enum.Enum):
    CASH_IN = "CASH_IN"
    CASH_OUT = "CASH_OUT"


class Shift(UUIDPKMixin, TenantScopedMixin, Base):
    """A cashier's session on one register, from opening the drawer to
    reconciling it at close. Sales/payments aren't tagged with a shift_id —
    instead a shift's cash activity is derived by register_id + time window
    (see services/shifts.py), so this stays additive to the sales model.
    """

    __tablename__ = "shifts"

    register_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("registers.id", ondelete="RESTRICT"), nullable=False, index=True)
    cashier_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)

    opening_cash: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    opening_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    actual_cash: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    expected_cash: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    variance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    closing_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closing_note: Mapped[str | None] = mapped_column(String(300), nullable=True)

    status: Mapped[ShiftStatus] = mapped_column(Enum(ShiftStatus, name="shift_status"), default=ShiftStatus.OPEN, nullable=False)

    cash_movements: Mapped[list["CashMovement"]] = relationship(back_populates="shift", cascade="all, delete-orphan")


class CashMovement(UUIDPKMixin, Base):
    __tablename__ = "cash_movements"

    shift_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False, index=True)
    performed_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    movement_type: Mapped[CashMovementType] = mapped_column(Enum(CashMovementType, name="cash_movement_type"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    shift: Mapped["Shift"] = relationship(back_populates="cash_movements")

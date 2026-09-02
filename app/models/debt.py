import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TenantScopedMixin, TimestampMixin, UUIDPKMixin
from app.models.sale import PaymentMethod


class Debt(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """One receivable, created for the unpaid portion of a single credit sale.

    A customer's total outstanding balance is ALWAYS
    SUM(balance) over that customer's Debt rows where cleared = false.
    Paying one debt only ever touches that debt's own `balance` — it must
    never overwrite any aggregate figure (that was the old system's bug).
    """

    __tablename__ = "debts"

    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    sale_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False)

    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)  # original receivable, immutable
    balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)  # remaining, decremented by payments
    cleared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    payments: Mapped[list["DebtPayment"]] = relationship(back_populates="debt", cascade="all, delete-orphan")


class DebtPayment(UUIDPKMixin, Base):
    __tablename__ = "debt_payments"

    debt_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("debts.id", ondelete="CASCADE"), nullable=False, index=True)
    received_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod, name="payment_method"), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(150), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    debt: Mapped["Debt"] = relationship(back_populates="payments")

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class SaleStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    VOIDED = "VOIDED"


class PaymentMethod(str, enum.Enum):
    CASH = "CASH"
    CARD = "CARD"
    MOBILE_MONEY = "MOBILE_MONEY"
    BANK = "BANK"
    OTHER = "OTHER"


class Sale(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "sales"

    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    register_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("registers.id", ondelete="SET NULL"), nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    cashier_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    sale_number: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    status: Mapped[SaleStatus] = mapped_column(Enum(SaleStatus, name="sale_status"), default=SaleStatus.COMPLETED, nullable=False)
    void_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["SaleItem"]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="sale", cascade="all, delete-orphan")


class SaleItem(UUIDPKMixin, Base):
    __tablename__ = "sale_items"

    sale_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)

    # Snapshots at time of sale — later product edits must never retroactively change history.
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit_selling_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    unit_cost_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)  # used for COGS in profit reports

    quantity: Mapped[int] = mapped_column(nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    sale: Mapped["Sale"] = relationship(back_populates="items")


class Payment(UUIDPKMixin, TenantScopedMixin, Base):
    """An actual amount collected. A sale may have zero (fully on credit),
    one, or several payment rows (split payment)."""

    __tablename__ = "payments"

    sale_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales.id", ondelete="CASCADE"), nullable=True, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    received_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod, name="payment_method"), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(150), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    sale: Mapped["Sale | None"] = relationship(back_populates="payments")

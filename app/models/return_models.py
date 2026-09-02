import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TenantScopedMixin, UUIDPKMixin


class SaleReturn(UUIDPKMixin, TenantScopedMixin, Base):
    """A partial or full return against a completed sale. Never mutates the
    original Sale/SaleItem rows — the sale stays an immutable record of what
    was actually sold; this is a separate, additive reversal (MASTER PROMPT
    §27 — returns/refunds are explicit transactions, not edits/deletes).
    """

    __tablename__ = "sale_returns"

    sale_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False, index=True)
    processed_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)  # total credited (to debt and/or cash)
    debt_reduction: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)  # portion applied to an open receivable
    cash_refund_due: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)  # portion the business owes back in cash/other

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    items: Mapped[list["SaleReturnItem"]] = relationship(back_populates="sale_return", cascade="all, delete-orphan")


class SaleReturnItem(UUIDPKMixin, Base):
    __tablename__ = "sale_return_items"

    sale_return_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sale_returns.id", ondelete="CASCADE"), nullable=False, index=True)
    sale_item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sale_items.id", ondelete="RESTRICT"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)

    quantity: Mapped[int] = mapped_column(nullable=False)
    line_refund_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    sale_return: Mapped["SaleReturn"] = relationship(back_populates="items")


class PurchaseReturn(UUIDPKMixin, TenantScopedMixin, Base):
    """The supplier-facing mirror of SaleReturn — stock bought back out,
    money the supplier owes the business (or a credit against a future
    purchase) tracked as refund_amount, informational until a supplier
    payable ledger exists."""

    __tablename__ = "purchase_returns"

    purchase_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("purchases.id", ondelete="RESTRICT"), nullable=False, index=True)
    processed_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    items: Mapped[list["PurchaseReturnItem"]] = relationship(back_populates="purchase_return", cascade="all, delete-orphan")


class PurchaseReturnItem(UUIDPKMixin, Base):
    __tablename__ = "purchase_return_items"

    purchase_return_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("purchase_returns.id", ondelete="CASCADE"), nullable=False, index=True)
    purchase_item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("purchase_items.id", ondelete="RESTRICT"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)

    quantity: Mapped[int] = mapped_column(nullable=False)
    line_refund_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    purchase_return: Mapped["PurchaseReturn"] = relationship(back_populates="items")

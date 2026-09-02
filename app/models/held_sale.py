import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from decimal import Decimal

from app.db.base import Base
from app.models.mixins import TenantScopedMixin, UUIDPKMixin


class HeldSale(UUIDPKMixin, TenantScopedMixin, Base):
    """A cashier's paused cart, held server-side so it survives a device
    change/reload and is auditable — the old localStorage-only design lost
    a held cart the moment the browser storage was cleared."""

    __tablename__ = "held_sales"

    register_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("registers.id", ondelete="SET NULL"), nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    cashier_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str | None] = mapped_column(String(150), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    items: Mapped[list["HeldSaleItem"]] = relationship(back_populates="held_sale", cascade="all, delete-orphan")


class HeldSaleItem(UUIDPKMixin, Base):
    __tablename__ = "held_sale_items"

    held_sale_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("held_sales.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    held_sale: Mapped["HeldSale"] = relationship(back_populates="items")

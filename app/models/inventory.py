import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TenantScopedMixin, UUIDPKMixin


class MovementType(str, enum.Enum):
    OPENING_BALANCE = "OPENING_BALANCE"
    PURCHASE = "PURCHASE"
    SALE = "SALE"
    SALE_RETURN = "SALE_RETURN"
    PURCHASE_RETURN = "PURCHASE_RETURN"
    ADJUSTMENT_IN = "ADJUSTMENT_IN"
    ADJUSTMENT_OUT = "ADJUSTMENT_OUT"
    DAMAGE = "DAMAGE"
    LOSS = "LOSS"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"


class InventoryMovement(UUIDPKMixin, TenantScopedMixin, Base):
    """Append-only audit ledger. product.current_stock is a cache kept in
    sync with this table inside the same DB transaction as every mutation —
    this table is what a stock reconciliation trusts, not the cache."""

    __tablename__ = "inventory_movements"

    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)

    movement_type: Mapped[MovementType] = mapped_column(Enum(MovementType, name="movement_type"), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)  # signed: positive = stock in, negative = stock out
    previous_quantity: Mapped[int] = mapped_column(nullable=False)
    resulting_quantity: Mapped[int] = mapped_column(nullable=False)

    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "sale" | "purchase" | ...
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)

    performed_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

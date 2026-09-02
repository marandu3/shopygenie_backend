import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TenantScopedMixin, UUIDPKMixin


class TransferStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    IN_TRANSIT = "IN_TRANSIT"
    RECEIVED = "RECEIVED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class InventoryTransfer(UUIDPKMixin, TenantScopedMixin, Base):
    """A branch-to-branch stock transfer's approval/logistics lifecycle.

    NOTE ON SCOPE: Product.current_stock is tracked per organization, not
    per branch (this schema has no per-branch stock table). A transfer here
    is a real, audited workflow — requested / approved / in transit /
    received / completed, each step attributable to a specific user — but
    it does NOT move quantity between two separate stock pools, because no
    such per-branch pools exist yet. Treat it as logistics/approval
    tracking, not a stock-quantity mutation."""

    __tablename__ = "inventory_transfers"

    source_branch_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    destination_branch_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)

    status: Mapped[TransferStatus] = mapped_column(Enum(TransferStatus, name="transfer_status"), default=TransferStatus.REQUESTED, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    received_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["InventoryTransferItem"]] = relationship(back_populates="transfer", cascade="all, delete-orphan")


class InventoryTransferItem(UUIDPKMixin, Base):
    __tablename__ = "inventory_transfer_items"

    transfer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("inventory_transfers.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)

    transfer: Mapped["InventoryTransfer"] = relationship(back_populates="items")

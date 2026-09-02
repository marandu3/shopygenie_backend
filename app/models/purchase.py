import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class PurchaseStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    VOIDED = "VOIDED"


class Purchase(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "purchases"

    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)
    purchased_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    purchase_number: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    status: Mapped[PurchaseStatus] = mapped_column(Enum(PurchaseStatus, name="purchase_status"), default=PurchaseStatus.COMPLETED, nullable=False)
    void_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["PurchaseItem"]] = relationship(back_populates="purchase", cascade="all, delete-orphan")


class PurchaseItem(UUIDPKMixin, Base):
    __tablename__ = "purchase_items"

    purchase_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)

    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    unit_cost_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    purchase: Mapped["Purchase"] = relationship(back_populates="items")

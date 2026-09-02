import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class Category(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_category_org_name"),)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Product(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("organization_id", "sku", name="uq_product_org_sku"),
        UniqueConstraint("organization_id", "barcode", name="uq_product_org_barcode"),
    )

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit: Mapped[str] = mapped_column(String(50), default="pcs", nullable=False)

    # Monetary values use fixed-point NUMERIC, never float, to avoid rounding drift.
    cost_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    # Cached for fast reads. The InventoryMovement ledger is the audit source of truth.
    current_stock: Mapped[int] = mapped_column(default=0, nullable=False)
    low_stock_alert: Mapped[int | None] = mapped_column(nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    category: Mapped["Category | None"] = relationship()

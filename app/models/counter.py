import uuid

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TenantScopedMixin, UUIDPKMixin


class DocumentCounter(UUIDPKMixin, TenantScopedMixin, Base):
    """Backs human-readable sequential document numbers (SALE-2026-000001,
    PURCHASE-2026-000001, ...). One row per (organization, key). Incremented
    with SELECT ... FOR UPDATE so concurrent requests never collide.
    """

    __tablename__ = "document_counters"
    __table_args__ = (UniqueConstraint("organization_id", "key", name="uq_counter_org_key"),)

    key: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "SALE-2026"
    value: Mapped[int] = mapped_column(default=0, nullable=False)

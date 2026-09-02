from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class Customer(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Note: there is deliberately NO stored `balance` column here.

    The old system stored a mutable `balance` field that got overwritten by
    single-debt payments, corrupting the true total when a customer had more
    than one open debt. Outstanding balance is now always derived as
    SUM(debts.balance WHERE cleared = false) — see services/customers.py.
    """

    __tablename__ = "customers"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

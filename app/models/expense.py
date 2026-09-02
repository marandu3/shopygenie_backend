import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TenantScopedMixin, TimestampMixin, UUIDPKMixin


class ExpenseCategory(UUIDPKMixin, TenantScopedMixin, Base):
    __tablename__ = "expense_categories"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Expense(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """A genuine operating expense (rent, electricity, salaries, ...).

    Deliberately NOT the same thing as inventory purchases or customer debt —
    the old system's profit formula wrongly folded both of those into
    "total_expenditures". See services/reports.py for the corrected formula.
    """

    __tablename__ = "expenses"

    category_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("expense_categories.id", ondelete="SET NULL"), nullable=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    recorded_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    description: Mapped[str] = mapped_column(String(300), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Path on disk (tenant/expense-isolated) of an uploaded receipt/photo —
    # never a public URL; served back through an auth-checked endpoint.
    evidence_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evidence_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

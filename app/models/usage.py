from sqlalchemy import String, UniqueConstraint

from app.db.base import Base
from app.models.mixins import TenantScopedMixin, UUIDPKMixin
from sqlalchemy.orm import Mapped, mapped_column


class UsageCounter(UUIDPKMixin, TenantScopedMixin, Base):
    """A metered feature's usage for one tenant in one calendar-month
    period. SMS/email stay unlimited while a subscription is active but are
    still counted here for transparency (MASTER PROMPT §63); any future
    metered channel (e.g. WhatsApp) increments through the same helper —
    see services/usage.py::increment_usage. No rollover between periods."""

    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("organization_id", "metric", "period", name="uq_usage_org_metric_period"),)

    metric: Mapped[str] = mapped_column(String(50), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # "YYYY-MM"
    count: Mapped[int] = mapped_column(default=0, nullable=False)

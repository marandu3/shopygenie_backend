import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage import UsageCounter


def current_period() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


async def increment_usage(db: AsyncSession, *, organization_id: uuid.UUID, metric: str, amount: int = 1) -> None:
    """SMS/email stay unlimited while a subscription is active but are still
    counted here for transparency (MASTER PROMPT §63); any future metered
    channel increments through this same helper. Best-effort — never blocks
    or fails the action it's counting."""
    period = current_period()
    result = await db.execute(
        select(UsageCounter).where(
            UsageCounter.organization_id == organization_id, UsageCounter.metric == metric, UsageCounter.period == period
        )
    )
    counter = result.scalar_one_or_none()
    if counter is None:
        counter = UsageCounter(organization_id=organization_id, metric=metric, period=period, count=0)
        db.add(counter)
    counter.count += amount
    await db.flush()


async def get_usage_summary(db: AsyncSession, *, organization_id: uuid.UUID, period: str | None = None) -> list[UsageCounter]:
    period = period or current_period()
    result = await db.execute(
        select(UsageCounter).where(UsageCounter.organization_id == organization_id, UsageCounter.period == period)
    )
    return list(result.scalars())

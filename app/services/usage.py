import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationAppError
from app.models.billing import BillingPlanConfig
from app.models.expense import Expense
from app.models.organization import Branch, Organization
from app.models.usage import UsageCounter
from app.models.user import User, WorkerStatus

WHATSAPP_METRIC = "whatsapp_messages"
SMS_METRIC = "sms_messages"


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


async def get_plan_config(db: AsyncSession, organization: Organization) -> BillingPlanConfig | None:
    if organization.subscription_plan is None:
        return None
    result = await db.execute(select(BillingPlanConfig).where(BillingPlanConfig.code == organization.subscription_plan))
    return result.scalar_one_or_none()


async def get_storage_used_bytes(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    """Real storage usage (MASTER PROMPT §64) — the sum of actually uploaded
    expense-evidence file sizes for this tenant, not a fabricated number."""
    result = await db.execute(
        select(func.coalesce(func.sum(Expense.evidence_size_bytes), 0)).where(Expense.organization_id == organization_id)
    )
    return int(result.scalar_one())


@dataclass
class QuotaCheck:
    used: int
    quota: int | None  # None = unlimited
    remaining: int | None
    percentage: float | None
    exhausted: bool
    warning: bool  # >= 80% of quota


def _evaluate_quota(used: int, quota: int | None) -> QuotaCheck:
    if quota is None:
        return QuotaCheck(used=used, quota=None, remaining=None, percentage=None, exhausted=False, warning=False)
    remaining = max(quota - used, 0)
    percentage = round((used / quota) * 100, 1) if quota > 0 else 100.0
    return QuotaCheck(
        used=used,
        quota=quota,
        remaining=remaining,
        percentage=percentage,
        exhausted=used >= quota,
        warning=quota > 0 and used / quota >= 0.8,
    )


async def check_whatsapp_quota(db: AsyncSession, organization: Organization) -> QuotaCheck:
    plan = await get_plan_config(db, organization)
    quota = plan.whatsapp_quota_monthly if plan else None
    counters = await get_usage_summary(db, organization_id=organization.id)
    used = next((c.count for c in counters if c.metric == WHATSAPP_METRIC), 0)
    return _evaluate_quota(used, quota)


async def check_storage_quota(db: AsyncSession, organization: Organization) -> QuotaCheck:
    plan = await get_plan_config(db, organization)
    quota_mb = plan.storage_quota_mb if plan else None
    quota_bytes = quota_mb * 1024 * 1024 if quota_mb is not None else None
    used = await get_storage_used_bytes(db, organization_id=organization.id)
    return _evaluate_quota(used, quota_bytes)


async def check_branch_quota(db: AsyncSession, organization: Organization) -> QuotaCheck:
    """MASTER PROMPT §67: features stay visible with an explanation and an
    upgrade path, rather than just failing when the limit is hit."""
    plan = await get_plan_config(db, organization)
    quota = plan.max_branches if plan else None
    count = (await db.execute(select(func.count()).select_from(Branch).where(Branch.organization_id == organization.id))).scalar_one()
    return _evaluate_quota(count, quota)


async def check_worker_quota(db: AsyncSession, organization: Organization) -> QuotaCheck:
    plan = await get_plan_config(db, organization)
    quota = plan.max_workers if plan else None
    count = (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(User.organization_id == organization.id, User.status.in_([WorkerStatus.ACTIVE, WorkerStatus.INVITED]))
        )
    ).scalar_one()
    return _evaluate_quota(count, quota)


async def enforce_whatsapp_quota(db: AsyncSession, organization: Organization) -> None:
    """Hard-block per MASTER PROMPT §66 — never silently fail."""
    check = await check_whatsapp_quota(db, organization)
    if check.exhausted:
        raise ValidationAppError(
            "WhatsApp message quota exhausted for this billing period. Upgrade your plan or wait for the next period.",
            code="WHATSAPP_QUOTA_EXHAUSTED",
        )


async def enforce_storage_quota(db: AsyncSession, organization: Organization, *, incoming_bytes: int) -> None:
    check = await check_storage_quota(db, organization)
    if check.quota is not None and check.used + incoming_bytes > check.quota:
        raise ValidationAppError(
            "This upload would exceed your organization's storage quota. Upgrade your plan or remove old evidence files.",
            code="STORAGE_QUOTA_EXHAUSTED",
        )


async def enforce_branch_limit(db: AsyncSession, organization: Organization) -> None:
    """Feature entitlement, not a usage meter (MASTER PROMPT §62, §67) — the
    plan's max_branches is a hard ceiling on how many branches can exist at
    once, checked before creating one more."""
    check = await check_branch_quota(db, organization)
    if check.exhausted:
        plan = await get_plan_config(db, organization)
        plan_name = plan.display_name if plan else "your current"
        raise ValidationAppError(
            f"Your {plan_name} plan allows up to {check.quota} branch(es). Upgrade your plan to add more.",
            code="BRANCH_LIMIT_REACHED",
        )


async def enforce_worker_limit(db: AsyncSession, organization: Organization) -> None:
    """Feature entitlement (MASTER PROMPT §62, §67) — active/invited workers
    count against the plan's max_workers ceiling; suspended/disabled ones
    don't, so removing access frees a seat."""
    check = await check_worker_quota(db, organization)
    if check.exhausted:
        plan = await get_plan_config(db, organization)
        plan_name = plan.display_name if plan else "your current"
        raise ValidationAppError(
            f"Your {plan_name} plan allows up to {check.quota} worker(s). Upgrade your plan to invite more.",
            code="WORKER_LIMIT_REACHED",
        )

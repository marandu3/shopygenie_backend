from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationAppError
from app.models.expense import Expense
from app.models.organization import Organization
from app.models.usage import UsageCounter
from app.schemas.platform_report import (
    ALLOWED_PLATFORM_METRICS,
    PlatformReportBuilderRequest,
    PlatformReportBuilderResult,
    PlatformReportBuilderRow,
)
from app.services.usage import SMS_METRIC, WHATSAPP_METRIC, current_period


async def build_platform_report(db: AsyncSession, *, request: PlatformReportBuilderRequest) -> PlatformReportBuilderResult:
    """Platform-level analytics only — every query here aggregates across
    organizations and never returns a single tenant's operational records
    (MASTER PROMPT §13, §60)."""
    if request.metric not in ALLOWED_PLATFORM_METRICS:
        raise ValidationAppError(f"Unknown platform metric: {request.metric}", code="INVALID_METRIC")

    if request.metric == "organizations_by_month":
        month_expr = func.to_char(Organization.created_at, "YYYY-MM")
        result = await db.execute(
            select(month_expr, func.count()).group_by(month_expr).order_by(month_expr)
        )
        rows = [PlatformReportBuilderRow(label=label, value=count) for label, count in result.all()]

    elif request.metric == "subscription_distribution":
        result = await db.execute(select(Organization.subscription_plan, func.count()).group_by(Organization.subscription_plan))
        rows = [
            PlatformReportBuilderRow(label=(plan.value if plan else "NONE"), value=count) for plan, count in result.all()
        ]

    elif request.metric == "sms_activity_by_month":
        result = await db.execute(
            select(UsageCounter.period, func.sum(UsageCounter.count))
            .where(UsageCounter.metric == SMS_METRIC)
            .group_by(UsageCounter.period)
            .order_by(UsageCounter.period)
        )
        rows = [PlatformReportBuilderRow(label=period, value=total) for period, total in result.all()]

    elif request.metric == "whatsapp_usage_by_plan":
        period = current_period()
        result = await db.execute(
            select(Organization.subscription_plan, func.coalesce(func.sum(UsageCounter.count), 0))
            .outerjoin(
                UsageCounter,
                (UsageCounter.organization_id == Organization.id)
                & (UsageCounter.metric == WHATSAPP_METRIC)
                & (UsageCounter.period == period),
            )
            .group_by(Organization.subscription_plan)
        )
        rows = [
            PlatformReportBuilderRow(label=(plan.value if plan else "NONE"), value=total) for plan, total in result.all()
        ]

    else:  # storage_consumption_by_plan
        result = await db.execute(
            select(Organization.subscription_plan, func.coalesce(func.sum(Expense.evidence_size_bytes), 0))
            .outerjoin(Expense, Expense.organization_id == Organization.id)
            .group_by(Organization.subscription_plan)
        )
        rows = [
            PlatformReportBuilderRow(label=(plan.value if plan else "NONE"), value=round(total_bytes / (1024 * 1024), 2))
            for plan, total_bytes in result.all()
        ]

    total = sum(r.value for r in rows)
    return PlatformReportBuilderResult(metric=request.metric, rows=rows, total=total)

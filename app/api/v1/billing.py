from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, PaginationParams, require_permission
from app.core.exceptions import NotFoundError
from app.core.permissions import BILLING_MANAGE, BILLING_VIEW
from app.db.session import get_db
from app.models.billing import ActivationRequest
from app.models.organization import Organization
from app.schemas.billing import ActivationRequestCreate, ActivationRequestOut, SubscriptionStatusOut
from app.schemas.common import Page
from app.schemas.usage import UsageMetricOut, UsageSummaryOut
from app.services.billing import submit_activation_request
from app.services.usage import current_period, get_usage_summary

router = APIRouter(prefix="/billing", tags=["Billing"])


@router.get("/usage", response_model=UsageSummaryOut)
async def get_usage_endpoint(
    ctx: AuthContext = Depends(require_permission(BILLING_VIEW)), db: AsyncSession = Depends(get_db)
):
    org_id = ctx.require_organization_id()
    period = current_period()
    counters = await get_usage_summary(db, organization_id=org_id, period=period)
    return UsageSummaryOut(
        period=period,
        metrics=[UsageMetricOut(metric=c.metric, period=c.period, count=c.count) for c in counters],
    )


@router.get("/status", response_model=SubscriptionStatusOut)
async def get_billing_status(
    ctx: AuthContext = Depends(require_permission(BILLING_VIEW)), db: AsyncSession = Depends(get_db)
):
    org = await db.get(Organization, ctx.require_organization_id())
    if org is None:
        raise NotFoundError("Organization not found")
    return SubscriptionStatusOut(
        subscription_status=org.subscription_status.value,
        subscription_plan=org.subscription_plan.value if org.subscription_plan else None,
        subscription_expires_at=org.subscription_expires_at,
    )


@router.post("/activation-requests", response_model=ActivationRequestOut, status_code=201)
async def create_activation_request(
    payload: ActivationRequestCreate,
    ctx: AuthContext = Depends(require_permission(BILLING_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    request = await submit_activation_request(
        db, organization_id=ctx.require_organization_id(), requested_by=ctx.user_id, payload=payload
    )
    await db.commit()
    await db.refresh(request)
    return request


@router.get("/activation-requests", response_model=Page[ActivationRequestOut])
async def list_my_activation_requests(
    ctx: AuthContext = Depends(require_permission(BILLING_VIEW)),
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
):
    org_id = ctx.require_organization_id()
    conditions = [ActivationRequest.organization_id == org_id]

    total = (await db.execute(select(func.count()).select_from(ActivationRequest).where(*conditions))).scalar_one()
    result = await db.execute(
        select(ActivationRequest)
        .where(*conditions)
        .order_by(ActivationRequest.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    return Page(items=list(result.scalars()), total=total, page=pagination.page, page_size=pagination.page_size)

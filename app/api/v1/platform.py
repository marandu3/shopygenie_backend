import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, PaginationParams, require_platform_owner
from app.core.exceptions import NotFoundError
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.account_request import AccountRequestStatus
from app.models.billing import ActivationRequestStatus
from app.models.organization import Organization
from app.models.user import User
from app.schemas.account_request import (
    AccountRequestApprove,
    AccountRequestReject,
    AccountRequestReview,
    TenantAccountRequestOut,
)
from app.schemas.billing import ActivationRequestAdminOut, ActivationRequestApprove, ActivationRequestReject
from app.schemas.common import Page
from app.schemas.platform import (
    EnterTenantResponse,
    OrganizationAdminOut,
    OrganizationProvision,
    PlatformKPIs,
)
from app.services.account_requests import (
    approve_account_request,
    reject_account_request,
    set_under_review,
)
from app.services.audit import log_action
from app.services.billing import approve_activation_request, platform_list_activation_requests, reject_activation_request
from app.services.notifications import send_sms
from app.services.platform import platform_kpis, provision_organization, set_organization_active
from app.services.workers import build_invitation_sms
from app.models.account_request import TenantAccountRequest

router = APIRouter(prefix="/platform", tags=["Platform"])


def _to_admin_out(request, organization_name: str) -> ActivationRequestAdminOut:
    # Built explicitly (not model_validate on the ORM row) because
    # organization_name isn't a column on ActivationRequest — it comes from
    # a join and has no value until we attach it here.
    return ActivationRequestAdminOut(
        id=request.id,
        organization_id=request.organization_id,
        requested_by=request.requested_by,
        plan_requested=request.plan_requested,
        reference_number=request.reference_number,
        note=request.note,
        status=request.status,
        reviewed_by=request.reviewed_by,
        reviewed_at=request.reviewed_at,
        review_note=request.review_note,
        created_at=request.created_at,
        organization_name=organization_name,
    )


@router.get("/kpis", response_model=PlatformKPIs)
async def get_platform_kpis(ctx: AuthContext = Depends(require_platform_owner), db: AsyncSession = Depends(get_db)):
    return await platform_kpis(db)


@router.get("/organizations", response_model=list[OrganizationAdminOut])
async def list_organizations(ctx: AuthContext = Depends(require_platform_owner), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Organization, func.count(User.id))
        .outerjoin(User, User.organization_id == Organization.id)
        .group_by(Organization.id)
        .order_by(Organization.created_at.desc())
    )
    out = []
    for org, worker_count in result.all():
        item = OrganizationAdminOut.model_validate(org, from_attributes=True)
        item.worker_count = worker_count
        out.append(item)
    return out


@router.post("/organizations", response_model=OrganizationAdminOut, status_code=201)
async def create_organization(
    payload: OrganizationProvision,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
):
    org, owner, temporary_password = await provision_organization(db, payload=payload, provisioned_by=ctx.user_id)
    await db.commit()
    await db.refresh(org)

    if owner.phone:
        message = build_invitation_sms(
            business_name=org.name, worker_name=owner.full_name, email=owner.email, temporary_password=temporary_password
        )
        background_tasks.add_task(send_sms, to=owner.phone, message=message)

    item = OrganizationAdminOut.model_validate(org, from_attributes=True)
    item.worker_count = 1
    return item


@router.post("/organizations/{organization_id}/suspend", response_model=OrganizationAdminOut)
async def suspend_organization(
    organization_id: uuid.UUID, ctx: AuthContext = Depends(require_platform_owner), db: AsyncSession = Depends(get_db)
):
    org = await set_organization_active(db, organization_id=organization_id, is_active=False, actor_id=ctx.user_id)
    await db.commit()
    await db.refresh(org)
    item = OrganizationAdminOut.model_validate(org, from_attributes=True)
    return item


@router.post("/organizations/{organization_id}/reactivate", response_model=OrganizationAdminOut)
async def reactivate_organization(
    organization_id: uuid.UUID, ctx: AuthContext = Depends(require_platform_owner), db: AsyncSession = Depends(get_db)
):
    org = await set_organization_active(db, organization_id=organization_id, is_active=True, actor_id=ctx.user_id)
    await db.commit()
    await db.refresh(org)
    item = OrganizationAdminOut.model_validate(org, from_attributes=True)
    return item


@router.post("/organizations/{organization_id}/enter", response_model=EnterTenantResponse)
async def enter_tenant_mode(
    organization_id: uuid.UUID,
    request: Request,
    ctx: AuthContext = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
):
    """Issues a short-lived access token carrying an explicit `act_org` claim
    so the platform owner can operate inside one tenant's data — this is
    audited on entry (and every action taken while in this mode is audited
    with acting_as_platform_owner=True). See MASTER PROMPT §6."""
    org = await db.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found")

    await log_action(
        db,
        actor_user_id=ctx.user_id,
        organization_id=organization_id,
        action="PLATFORM_OWNER_ENTERED_TENANT",
        resource_type="organization",
        resource_id=str(organization_id),
        acting_as_platform_owner=True,
        request=request,
    )
    await db.commit()

    access_token = create_access_token(ctx.user_id, extra_claims={"act_org": str(organization_id)})
    return EnterTenantResponse(access_token=access_token, organization_id=organization_id, organization_name=org.name)


@router.get("/activation-requests", response_model=Page[ActivationRequestAdminOut])
async def list_activation_requests(
    status: ActivationRequestStatus | None = None,
    ctx: AuthContext = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
):
    """Every tenant's billing-activation claims, across all organizations —
    this is the platform owner's manual-verification queue (no payment
    gateway is wired; each claim is checked against the reference number by
    a human before the organization's subscription is activated)."""
    rows, total = await platform_list_activation_requests(
        db, status_filter=status, offset=pagination.offset, limit=pagination.limit
    )
    items = [_to_admin_out(request, org_name) for request, org_name in rows]
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.post("/activation-requests/{request_id}/approve", response_model=ActivationRequestAdminOut)
async def approve_activation_request_endpoint(
    request_id: uuid.UUID,
    payload: ActivationRequestApprove,
    ctx: AuthContext = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
):
    request = await approve_activation_request(db, request_id=request_id, actor_id=ctx.user_id, payload=payload)
    org = await db.get(Organization, request.organization_id)
    await db.commit()
    await db.refresh(request)
    return _to_admin_out(request, org.name if org else "")


@router.post("/activation-requests/{request_id}/reject", response_model=ActivationRequestAdminOut)
async def reject_activation_request_endpoint(
    request_id: uuid.UUID,
    payload: ActivationRequestReject,
    ctx: AuthContext = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
):
    request = await reject_activation_request(db, request_id=request_id, actor_id=ctx.user_id, payload=payload)
    org = await db.get(Organization, request.organization_id)
    await db.commit()
    await db.refresh(request)
    return _to_admin_out(request, org.name if org else "")


# ---------- Tenant account requests (MASTER PROMPT §7) ----------

@router.get("/account-requests", response_model=Page[TenantAccountRequestOut])
async def list_account_requests(
    status: AccountRequestStatus | None = None,
    ctx: AuthContext = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
):
    conditions = [TenantAccountRequest.status == status] if status else []
    total = (await db.execute(select(func.count()).select_from(TenantAccountRequest).where(*conditions))).scalar_one()
    result = await db.execute(
        select(TenantAccountRequest).where(*conditions).order_by(TenantAccountRequest.created_at.desc())
        .offset(pagination.offset).limit(pagination.limit)
    )
    items = list(result.scalars())
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.post("/account-requests/{request_id}/review", response_model=TenantAccountRequestOut)
async def review_account_request_endpoint(
    request_id: uuid.UUID, payload: AccountRequestReview, ctx: AuthContext = Depends(require_platform_owner), db: AsyncSession = Depends(get_db)
):
    request = await set_under_review(db, request_id=request_id, actor_id=ctx.user_id, note=payload.note)
    await db.commit()
    return request


@router.post("/account-requests/{request_id}/reject", response_model=TenantAccountRequestOut)
async def reject_account_request_endpoint(
    request_id: uuid.UUID, payload: AccountRequestReject, ctx: AuthContext = Depends(require_platform_owner), db: AsyncSession = Depends(get_db)
):
    request = await reject_account_request(db, request_id=request_id, actor_id=ctx.user_id, note=payload.note)
    await db.commit()
    return request


@router.post("/account-requests/{request_id}/approve", response_model=TenantAccountRequestOut)
async def approve_account_request_endpoint(
    request_id: uuid.UUID,
    payload: AccountRequestApprove,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
):
    request, org, owner, temporary_password = await approve_account_request(db, request_id=request_id, actor_id=ctx.user_id, payload=payload)
    await db.commit()
    await db.refresh(request)

    if owner.phone:
        message = build_invitation_sms(
            business_name=org.name, worker_name=owner.full_name, email=owner.email, temporary_password=temporary_password
        )
        background_tasks.add_task(send_sms, to=owner.phone, message=message)

    return request

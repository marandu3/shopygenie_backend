import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_platform_owner
from app.core.exceptions import NotFoundError
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.platform import (
    EnterTenantResponse,
    OrganizationAdminOut,
    OrganizationProvision,
    PlatformKPIs,
)
from app.services.audit import log_action
from app.services.notifications import send_sms
from app.services.platform import platform_kpis, provision_organization, set_organization_active
from app.services.workers import build_invitation_sms

router = APIRouter(prefix="/platform", tags=["Platform"])


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

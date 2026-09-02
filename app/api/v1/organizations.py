import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission, require_tenant_context
from app.core.exceptions import NotFoundError
from app.core.permissions import SETTINGS_MANAGE
from app.db.session import get_db
from app.models.billing import SmsMessage, SmsMessageType
from app.models.organization import Branch, Organization, Register
from app.schemas.common import Page
from app.schemas.organization import (
    BranchCreate,
    BranchOut,
    OrganizationOut,
    OrganizationSettingsUpdate,
    RegisterCreate,
    RegisterOut,
)
from app.schemas.sms import SmsConfigOut, SmsConfigUpdate, SmsMessageOut, SmsTestRequest
from app.services.notifications import send_sms
from app.services.sms_config import get_sms_config, record_test_result, update_sms_config
from app.services.usage import enforce_branch_limit

router = APIRouter(prefix="/organizations", tags=["Organization"])


@router.get("/me", response_model=OrganizationOut)
async def get_my_organization(ctx: AuthContext = Depends(require_tenant_context), db: AsyncSession = Depends(get_db)):
    org = await db.get(Organization, ctx.require_organization_id())
    if org is None:
        raise NotFoundError("Organization not found")
    return org


@router.put("/me", response_model=OrganizationOut)
async def update_my_organization(
    payload: OrganizationSettingsUpdate,
    ctx: AuthContext = Depends(require_permission(SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, ctx.require_organization_id())
    if org is None:
        raise NotFoundError("Organization not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(org, field, value)

    await db.commit()
    await db.refresh(org)
    return org


@router.post("/me/branches", response_model=BranchOut, status_code=201)
async def create_branch(
    payload: BranchCreate,
    ctx: AuthContext = Depends(require_permission(SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    org = await db.get(Organization, org_id)
    if org is None:
        raise NotFoundError("Organization not found")
    await enforce_branch_limit(db, org)

    branch = Branch(organization_id=org_id, **payload.model_dump())
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    return branch


@router.get("/me/branches", response_model=list[BranchOut])
async def list_branches(ctx: AuthContext = Depends(require_tenant_context), db: AsyncSession = Depends(get_db)):
    org_id = ctx.require_organization_id()
    result = await db.execute(select(Branch).where(Branch.organization_id == org_id).order_by(Branch.name))
    return list(result.scalars())


@router.post("/me/registers", response_model=RegisterOut, status_code=201)
async def create_register(
    payload: RegisterCreate,
    ctx: AuthContext = Depends(require_permission(SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    branch = await db.get(Branch, payload.branch_id)
    if branch is None or branch.organization_id != org_id:
        raise NotFoundError("Branch not found")

    register = Register(organization_id=org_id, **payload.model_dump())
    db.add(register)
    await db.commit()
    await db.refresh(register)
    return register


@router.get("/me/registers", response_model=list[RegisterOut])
async def list_registers(ctx: AuthContext = Depends(require_tenant_context), db: AsyncSession = Depends(get_db)):
    org_id = ctx.require_organization_id()
    result = await db.execute(select(Register).where(Register.organization_id == org_id).order_by(Register.name))
    return list(result.scalars())


# ---------- Tenant SMSGate configuration (MASTER PROMPT §43, §44) ----------


@router.get("/me/sms-config", response_model=SmsConfigOut)
async def get_sms_config_endpoint(
    ctx: AuthContext = Depends(require_permission(SETTINGS_MANAGE)), db: AsyncSession = Depends(get_db)
):
    return await get_sms_config(db, organization_id=ctx.require_organization_id())


@router.put("/me/sms-config", response_model=SmsConfigOut)
async def update_sms_config_endpoint(
    payload: SmsConfigUpdate,
    ctx: AuthContext = Depends(require_permission(SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    result = await update_sms_config(db, organization_id=ctx.require_organization_id(), actor_id=ctx.user_id, payload=payload)
    await db.commit()
    return result


@router.post("/me/sms-config/test", response_model=SmsMessageOut)
async def test_sms_config_endpoint(
    payload: SmsTestRequest,
    ctx: AuthContext = Depends(require_permission(SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    # Runs inline (not a background task) so the caller sees the real
    # success/failure immediately, per the "Test the connection / Send a
    # test SMS" steps in the setup guide (MASTER PROMPT §44).
    await db.commit()  # flush any pending config changes before send_sms opens its own session
    log = await send_sms(
        organization_id=org_id,
        to=payload.phone,
        message="This is a test message from ShopyGenie. Your SMSGate configuration is working.",
        message_type=SmsMessageType.TEST,
        sent_by=ctx.user_id,
    )
    await record_test_result(
        db, organization_id=org_id, success=(log.status.value == "SENT"), error=log.error
    )
    await db.commit()
    return log


@router.get("/me/sms-history", response_model=Page[SmsMessageOut])
async def list_sms_history(
    ctx: AuthContext = Depends(require_permission(SETTINGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    page_size: int = 25,
):
    org_id = ctx.require_organization_id()
    conditions = [SmsMessage.organization_id == org_id]
    total = (await db.execute(select(func.count()).select_from(SmsMessage).where(*conditions))).scalar_one()
    result = await db.execute(
        select(SmsMessage)
        .where(*conditions)
        .order_by(SmsMessage.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(items=list(result.scalars()), total=total, page=page, page_size=page_size)

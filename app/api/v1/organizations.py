import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission, require_tenant_context
from app.core.exceptions import NotFoundError
from app.core.permissions import SETTINGS_MANAGE
from app.db.session import get_db
from app.models.organization import Branch, Organization, Register
from app.schemas.organization import (
    BranchCreate,
    BranchOut,
    OrganizationOut,
    OrganizationSettingsUpdate,
    RegisterCreate,
    RegisterOut,
)

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

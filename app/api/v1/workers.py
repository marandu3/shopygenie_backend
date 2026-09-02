import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import AuthContext, require_permission, require_tenant_context
from app.core.exceptions import NotFoundError
from app.core.permissions import ROLES_MANAGE, WORKERS_INVITE, WORKERS_SUSPEND, WORKERS_UPDATE
from app.db.session import get_db
from app.models.billing import SmsMessageType
from app.models.organization import Organization
from app.models.user import Permission, Role, RolePermission, User, WorkerStatus
from app.schemas.user import PermissionOut, RoleCreate, RoleOut, RoleUpdate, WorkerInvite, WorkerOut, WorkerUpdate
from app.services.notifications import send_sms
from app.services.workers import (
    build_invitation_sms,
    create_custom_role,
    delete_custom_role,
    invite_worker,
    set_worker_status,
    update_custom_role,
)

router = APIRouter(prefix="/workers", tags=["Workers"])


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(ctx: AuthContext = Depends(require_tenant_context), db: AsyncSession = Depends(get_db)):
    org_id = ctx.require_organization_id()
    result = await db.execute(
        select(Role)
        .where(or_(Role.organization_id.is_(None), Role.organization_id == org_id))
        .options(selectinload(Role.permissions).selectinload(RolePermission.permission))
        .order_by(Role.name)
    )
    roles = result.scalars().unique().all()
    out = []
    for role in roles:
        out.append(RoleOut(id=role.id, name=role.name, is_system=role.is_system, permissions=[rp.permission.code for rp in role.permissions]))
    return out


@router.get("/permissions", response_model=list[PermissionOut])
async def list_permissions(ctx: AuthContext = Depends(require_tenant_context), db: AsyncSession = Depends(get_db)):
    """Full permission catalog, for building a custom-role checkbox UI
    (MASTER PROMPT §42)."""
    result = await db.execute(select(Permission).order_by(Permission.code))
    return list(result.scalars())


@router.post("/roles", response_model=RoleOut, status_code=201)
async def create_role_endpoint(
    payload: RoleCreate, ctx: AuthContext = Depends(require_permission(ROLES_MANAGE)), db: AsyncSession = Depends(get_db)
):
    org_id = ctx.require_organization_id()
    role = await create_custom_role(db, organization_id=org_id, actor_id=ctx.user_id, payload=payload)
    await db.commit()
    return RoleOut(id=role.id, name=role.name, is_system=role.is_system, permissions=[rp.permission.code for rp in role.permissions])


@router.put("/roles/{role_id}", response_model=RoleOut)
async def update_role_endpoint(
    role_id: uuid.UUID,
    payload: RoleUpdate,
    ctx: AuthContext = Depends(require_permission(ROLES_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    role = await update_custom_role(db, organization_id=org_id, role_id=role_id, actor_id=ctx.user_id, payload=payload)
    await db.commit()
    return RoleOut(id=role.id, name=role.name, is_system=role.is_system, permissions=[rp.permission.code for rp in role.permissions])


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role_endpoint(
    role_id: uuid.UUID, ctx: AuthContext = Depends(require_permission(ROLES_MANAGE)), db: AsyncSession = Depends(get_db)
):
    org_id = ctx.require_organization_id()
    await delete_custom_role(db, organization_id=org_id, role_id=role_id, actor_id=ctx.user_id)
    await db.commit()


@router.post("", response_model=WorkerOut, status_code=201)
async def invite_worker_endpoint(
    payload: WorkerInvite,
    background_tasks: BackgroundTasks,
    ctx: AuthContext = Depends(require_permission(WORKERS_INVITE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    org = await db.get(Organization, org_id)

    worker, temporary_password = await invite_worker(db, organization_id=org_id, invited_by=ctx.user_id, payload=payload)
    await db.commit()
    await db.refresh(worker)

    if worker.phone:
        message = build_invitation_sms(
            business_name=org.name, worker_name=worker.full_name, email=worker.email, temporary_password=temporary_password
        )
        # Fire-and-forget: never make the invite request wait on SMS delivery (MASTER PROMPT §41).
        # send_sms opens its own DB session and logs the attempt + counts usage itself.
        background_tasks.add_task(
            send_sms,
            organization_id=org_id,
            to=worker.phone,
            message=message,
            message_type=SmsMessageType.WORKER_INVITE,
            sent_by=ctx.user_id,
        )

    return worker


@router.get("", response_model=list[WorkerOut])
async def list_workers(ctx: AuthContext = Depends(require_tenant_context), db: AsyncSession = Depends(get_db)):
    org_id = ctx.require_organization_id()
    result = await db.execute(select(User).where(User.organization_id == org_id).order_by(User.full_name))
    return list(result.scalars())


@router.put("/{worker_id}", response_model=WorkerOut)
async def update_worker(
    worker_id: uuid.UUID,
    payload: WorkerUpdate,
    ctx: AuthContext = Depends(require_permission(WORKERS_UPDATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    worker = await db.get(User, worker_id)
    if worker is None or worker.organization_id != org_id:
        raise NotFoundError("Worker not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(worker, field, value)

    await db.commit()
    await db.refresh(worker)
    return worker


@router.post("/{worker_id}/suspend", response_model=WorkerOut)
async def suspend_worker(
    worker_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission(WORKERS_SUSPEND)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    worker = await set_worker_status(db, organization_id=org_id, worker_id=worker_id, status=WorkerStatus.SUSPENDED, actor_id=ctx.user_id)
    await db.commit()
    await db.refresh(worker)
    return worker


@router.post("/{worker_id}/reactivate", response_model=WorkerOut)
async def reactivate_worker(
    worker_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission(WORKERS_SUSPEND)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    worker = await set_worker_status(db, organization_id=org_id, worker_id=worker_id, status=WorkerStatus.ACTIVE, actor_id=ctx.user_id)
    await db.commit()
    await db.refresh(worker)
    return worker

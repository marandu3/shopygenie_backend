from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, PaginationParams, require_permission, require_platform_owner
from app.core.permissions import AUDIT_VIEW
from app.db.session import get_db
from app.models.audit import AuditLog
from app.schemas.audit import AuditLogOut
from app.schemas.common import Page

router = APIRouter(prefix="/audit-logs", tags=["Audit"])


@router.get("", response_model=Page[AuditLogOut])
async def list_audit_logs(
    ctx: AuthContext = Depends(require_permission(AUDIT_VIEW)),
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
):
    org_id = ctx.require_organization_id()
    conditions = [AuditLog.organization_id == org_id]

    total = (await db.execute(select(func.count()).select_from(AuditLog).where(*conditions))).scalar_one()
    result = await db.execute(
        select(AuditLog).where(*conditions).order_by(AuditLog.created_at.desc()).offset(pagination.offset).limit(pagination.limit)
    )
    return Page(items=list(result.scalars()), total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/platform", response_model=Page[AuditLogOut])
async def list_platform_audit_logs(
    ctx: AuthContext = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
):
    """Platform-wide audit trail — every tenant, every platform-owner action.
    Restricted to the platform owner (never a tenant's own audit view)."""
    total = (await db.execute(select(func.count()).select_from(AuditLog))).scalar_one()
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).offset(pagination.offset).limit(pagination.limit)
    )
    return Page(items=list(result.scalars()), total=total, page=pagination.page, page_size=pagination.page_size)

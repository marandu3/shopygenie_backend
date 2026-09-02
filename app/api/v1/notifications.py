import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, PaginationParams, require_password_already_set
from app.core.exceptions import ForbiddenError
from app.db.session import get_db
from app.models.notification import Notification
from app.schemas.common import Page
from app.schemas.notification import NotificationOut, UnreadCountOut
from app.services.notification_center import list_notifications, mark_all_read, mark_read, unread_count

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _scope_org_id(ctx: AuthContext) -> uuid.UUID | None:
    """Tenant users see their org's notifications; a platform owner not
    currently in tenant mode sees the platform-wide (organization_id IS
    NULL) feed instead — mirrors AuthContext.organization_id semantics."""
    if ctx.organization_id is not None:
        return ctx.organization_id
    if ctx.is_platform_owner:
        return None
    raise ForbiddenError("This action requires an active tenant context")


def _to_out(notification: Notification, is_read: bool) -> NotificationOut:
    return NotificationOut(
        id=notification.id,
        organization_id=notification.organization_id,
        type=notification.type,
        title=notification.title,
        body=notification.body,
        link=notification.link,
        resource_type=notification.resource_type,
        resource_id=notification.resource_id,
        created_at=notification.created_at,
        is_read=is_read,
    )


@router.get("", response_model=Page[NotificationOut])
async def list_my_notifications(
    ctx: AuthContext = Depends(require_password_already_set),
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
):
    org_id = _scope_org_id(ctx)
    rows, total = await list_notifications(
        db, organization_id=org_id, user_id=ctx.user_id, offset=pagination.offset, limit=pagination.limit
    )
    items = [_to_out(notification, bool(is_read)) for notification, is_read in rows]
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/unread-count", response_model=UnreadCountOut)
async def get_unread_count(
    ctx: AuthContext = Depends(require_password_already_set), db: AsyncSession = Depends(get_db)
):
    org_id = _scope_org_id(ctx)
    count = await unread_count(db, organization_id=org_id, user_id=ctx.user_id)
    return UnreadCountOut(unread_count=count)


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: uuid.UUID,
    ctx: AuthContext = Depends(require_password_already_set),
    db: AsyncSession = Depends(get_db),
):
    await mark_read(db, notification_id=notification_id, user_id=ctx.user_id)
    await db.commit()
    return {"detail": "ok"}


@router.post("/read-all")
async def mark_all_notifications_read(
    ctx: AuthContext = Depends(require_password_already_set), db: AsyncSession = Depends(get_db)
):
    org_id = _scope_org_id(ctx)
    await mark_all_read(db, organization_id=org_id, user_id=ctx.user_id)
    await db.commit()
    return {"detail": "ok"}

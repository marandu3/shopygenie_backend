import uuid
from datetime import datetime, timezone

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationRead, NotificationType


async def create_notification(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID | None,
    type: NotificationType,
    title: str,
    body: str,
    link: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> Notification:
    """Add this to the same transaction as the event it describes (mirrors
    log_action's contract) — a notification should never exist without, or
    diverge from, the change it's telling someone about."""
    notification = Notification(
        organization_id=organization_id,
        type=type,
        title=title,
        body=body,
        link=link,
        resource_type=resource_type,
        resource_id=resource_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(notification)
    await db.flush()
    return notification


def _scope_conditions(organization_id: uuid.UUID | None):
    return [Notification.organization_id == organization_id] if organization_id else [Notification.organization_id.is_(None)]


def _read_exists(user_id: uuid.UUID):
    return exists().where(NotificationRead.notification_id == Notification.id, NotificationRead.user_id == user_id)


async def list_notifications(
    db: AsyncSession, *, organization_id: uuid.UUID | None, user_id: uuid.UUID, offset: int, limit: int
) -> tuple[list[tuple[Notification, bool]], int]:
    conditions = _scope_conditions(organization_id)
    read_exists = _read_exists(user_id)

    total = (await db.execute(select(func.count()).select_from(Notification).where(*conditions))).scalar_one()
    result = await db.execute(
        select(Notification, read_exists.label("is_read"))
        .where(*conditions)
        .order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.all()), total


async def unread_count(db: AsyncSession, *, organization_id: uuid.UUID | None, user_id: uuid.UUID) -> int:
    conditions = _scope_conditions(organization_id)
    read_exists = _read_exists(user_id)
    result = await db.execute(select(func.count()).select_from(Notification).where(*conditions, ~read_exists))
    return result.scalar_one()


async def mark_read(db: AsyncSession, *, notification_id: uuid.UUID, user_id: uuid.UUID) -> None:
    existing = await db.execute(
        select(NotificationRead).where(
            NotificationRead.notification_id == notification_id, NotificationRead.user_id == user_id
        )
    )
    if existing.scalar_one_or_none() is not None:
        return
    db.add(NotificationRead(notification_id=notification_id, user_id=user_id, read_at=datetime.now(timezone.utc)))
    await db.flush()


async def mark_all_read(db: AsyncSession, *, organization_id: uuid.UUID | None, user_id: uuid.UUID) -> None:
    conditions = _scope_conditions(organization_id)
    read_exists = _read_exists(user_id)
    result = await db.execute(select(Notification.id).where(*conditions, ~read_exists))
    ids = [row[0] for row in result.all()]
    now = datetime.now(timezone.utc)
    for notification_id in ids:
        db.add(NotificationRead(notification_id=notification_id, user_id=user_id, read_at=now))
    await db.flush()

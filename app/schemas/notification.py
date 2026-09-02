import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.notification import NotificationType
from app.schemas.common import ORMModel


class NotificationOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID | None
    type: NotificationType
    title: str
    body: str
    link: str | None
    resource_type: str | None
    resource_id: str | None
    created_at: datetime
    is_read: bool


class UnreadCountOut(BaseModel):
    unread_count: int

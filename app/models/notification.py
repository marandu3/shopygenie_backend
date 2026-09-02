import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPKMixin


class NotificationType(str, enum.Enum):
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ACTION_REQUIRED = "ACTION_REQUIRED"


class Notification(UUIDPKMixin, Base):
    """A user-facing notice — distinct from AuditLog (a forensic WHO/WHAT/WHEN
    record). organization_id is nullable: a null-scoped notification targets
    every platform owner (e.g. "new activation request awaiting review").
    Read state is per-user (see NotificationRead) since one notification can
    be seen by every member of an organization."""

    __tablename__ = "notifications"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, name="notification_type"), default=NotificationType.INFO, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationRead(Base):
    """Per-user read receipt. A notification is org-wide; whether *you* have
    seen it is tracked here rather than by mutating the notification itself."""

    __tablename__ = "notification_reads"

    notification_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

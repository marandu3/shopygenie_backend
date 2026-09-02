import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPKMixin


class PlatformOwnerInvitationStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class PlatformOwnerInvitation(UUIDPKMixin, Base):
    """A platform owner inviting another. The accepted user becomes a
    platform owner belonging to the dedicated Platform Organization (see
    scripts/seed.py) — Platform Mode plus normal Tenant Mode inside that
    one org, never implicit access to any other tenant (that still only
    ever happens through the audited act_org "enter tenant" flow)."""

    __tablename__ = "platform_owner_invitations"

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[PlatformOwnerInvitationStatus] = mapped_column(
        Enum(PlatformOwnerInvitationStatus, name="platform_owner_invitation_status"),
        default=PlatformOwnerInvitationStatus.PENDING,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.platform_owner_invitation import PlatformOwnerInvitationStatus
from app.schemas.common import ORMModel


class PlatformOwnerInvitationCreate(BaseModel):
    email: EmailStr


class PlatformOwnerInvitationOut(ORMModel):
    id: uuid.UUID
    email: str
    status: PlatformOwnerInvitationStatus
    expires_at: datetime
    created_at: datetime


class PlatformOwnerInvitationCreated(PlatformOwnerInvitationOut):
    token: str  # only ever returned once, at creation


class PlatformOwnerInvitationAccept(BaseModel):
    token: str
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)

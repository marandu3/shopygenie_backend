import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class WorkerInvite(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    phone: str | None = None
    email: EmailStr
    role_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    register_id: uuid.UUID | None = None


class WorkerUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    role_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    register_id: uuid.UUID | None = None


class WorkerOut(ORMModel):
    id: uuid.UUID
    full_name: str
    email: str
    phone: str | None
    role_id: uuid.UUID | None
    branch_id: uuid.UUID | None
    register_id: uuid.UUID | None
    status: str
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime


class RoleOut(ORMModel):
    id: uuid.UUID
    name: str
    is_system: bool
    permissions: list[str] = []

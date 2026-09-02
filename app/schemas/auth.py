import uuid

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    must_change_password: bool = False


class RefreshRequest(BaseModel):
    # Only needed for non-browser clients; browsers get it via httpOnly cookie.
    refresh_token: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str | None = None  # not required on the forced first change
    new_password: str = Field(min_length=8, max_length=128)


class CurrentUser(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID | None
    full_name: str
    email: str
    is_platform_owner: bool
    must_change_password: bool
    role_name: str | None = None
    permissions: list[str] = []

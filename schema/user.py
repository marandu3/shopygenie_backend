from pydantic import BaseModel, EmailStr
from enum import Enum

class UserRole(str, Enum):
    admin = "admin"
    user = "user"


# ──────────────────────────────────────────────
# Input schema: for creating a user (from client)
class Usercreate(BaseModel):
    username: str
    email: EmailStr
    password: str   # plain password from client


# ──────────────────────────────────────────────
# For updating user profile (not password)
class Userupdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None


# ──────────────────────────────────────────────
# Internal representation (stored in DB)
class UserInDB(BaseModel):
    id: int
    username: str
    email: EmailStr
    hashed_password: str
    role: UserRole = UserRole.user


# ──────────────────────────────────────────────
# What you return to the client (public data)
class UserInResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: UserRole = UserRole.user


# ──────────────────────────────────────────────
# For login requests
class UserLogin(BaseModel):
    username: str
    password: str

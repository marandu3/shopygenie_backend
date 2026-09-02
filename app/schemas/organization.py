import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class BranchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    address: str | None = None


class BranchOut(ORMModel):
    id: uuid.UUID
    name: str
    address: str | None
    is_active: bool


class RegisterCreate(BaseModel):
    branch_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=50)


class RegisterOut(ORMModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    name: str
    code: str
    is_active: bool


class OrganizationOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    currency: str
    timezone: str
    tax_rate_percent: float
    tax_inclusive_pricing: bool
    low_stock_default_threshold: int
    subscription_status: str
    is_active: bool
    created_at: datetime


class OrganizationSettingsUpdate(BaseModel):
    name: str | None = None
    currency: str | None = None
    timezone: str | None = None
    tax_rate_percent: float | None = Field(default=None, ge=0, le=100)
    tax_inclusive_pricing: bool | None = None
    low_stock_default_threshold: int | None = Field(default=None, ge=0)

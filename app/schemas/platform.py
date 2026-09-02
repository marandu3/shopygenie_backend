import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class OrganizationProvision(BaseModel):
    """Platform owner creates a brand-new tenant + its first (owner) user."""

    organization_name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=200)
    owner_full_name: str = Field(min_length=1, max_length=200)
    owner_email: EmailStr
    owner_phone: str | None = None
    currency: str = "TZS"


class OrganizationAdminOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    subscription_status: str
    is_active: bool
    created_at: datetime
    worker_count: int = 0


class PlatformKPIs(BaseModel):
    total_organizations: int
    active_organizations: int
    suspended_organizations: int
    total_workers: int
    total_sales_all_time: float
    generated_at: datetime


class EnterTenantResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    organization_id: uuid.UUID
    organization_name: str

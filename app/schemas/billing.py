import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.billing import ActivationRequestStatus
from app.models.organization import SubscriptionPlan
from app.schemas.common import ORMModel


class ActivationRequestCreate(BaseModel):
    plan_requested: SubscriptionPlan
    reference_number: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)


class ActivationRequestOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    requested_by: uuid.UUID
    plan_requested: SubscriptionPlan
    reference_number: str
    note: str | None
    status: ActivationRequestStatus
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime


class ActivationRequestAdminOut(ActivationRequestOut):
    organization_name: str


class ActivationRequestApprove(BaseModel):
    duration_days: int = Field(default=30, ge=1, le=3650)
    review_note: str | None = Field(default=None, max_length=500)


class ActivationRequestReject(BaseModel):
    review_note: str = Field(min_length=1, max_length=500)


class SubscriptionStatusOut(BaseModel):
    subscription_status: str
    subscription_plan: str | None
    subscription_expires_at: datetime | None


class BillingPlanOut(ORMModel):
    """MASTER PROMPT §61: names/descriptions/prices/quotas are configurable
    by Platform Owners — this is the public shape shown on pricing pages."""

    id: uuid.UUID
    code: SubscriptionPlan
    display_name: str
    description: str
    price_monthly: float
    currency: str
    max_branches: int | None
    max_workers: int | None
    whatsapp_quota_monthly: int | None
    storage_quota_mb: int | None
    is_active: bool
    sort_order: int


class BillingPlanUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    price_monthly: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    max_branches: int | None = Field(default=None, ge=0)
    max_workers: int | None = Field(default=None, ge=0)
    whatsapp_quota_monthly: int | None = Field(default=None, ge=0)
    storage_quota_mb: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    sort_order: int | None = None

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

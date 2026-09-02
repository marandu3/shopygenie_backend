import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.account_request import AccountRequestStatus
from app.schemas.common import ORMModel


class TenantAccountRequestCreate(BaseModel):
    organization_name: str = Field(min_length=1, max_length=200)
    applicant_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = None
    business_type: str | None = None
    location: str | None = None
    expected_usage: str | None = None
    additional_info: str | None = None


class TenantAccountRequestOut(ORMModel):
    id: uuid.UUID
    organization_name: str
    applicant_name: str
    email: str
    phone: str | None
    business_type: str | None
    location: str | None
    expected_usage: str | None
    additional_info: str | None
    status: AccountRequestStatus
    review_note: str | None
    organization_id: uuid.UUID | None
    created_at: datetime


class AccountRequestReview(BaseModel):
    note: str | None = None


class AccountRequestReject(BaseModel):
    note: str = Field(min_length=1, max_length=500)


class AccountRequestApprove(BaseModel):
    slug: str = Field(min_length=1, max_length=200)
    currency: str = "TZS"

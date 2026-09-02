import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class SmsConfigUpdate(BaseModel):
    base_url: str | None = Field(default=None, max_length=300)
    api_key: str | None = Field(default=None, min_length=1, max_length=500)
    sender_id: str | None = Field(default=None, max_length=50)
    enabled: bool | None = None


class SmsConfigOut(BaseModel):
    enabled: bool
    base_url: str | None
    sender_id: str | None
    api_key_masked: str | None
    last_tested_at: datetime | None
    last_test_status: str | None
    last_test_error: str | None


class SmsTestRequest(BaseModel):
    phone: str = Field(min_length=5, max_length=30)


class SmsMessageOut(ORMModel):
    id: uuid.UUID
    message_type: str
    recipient: str
    body: str
    status: str
    provider_message_id: str | None
    error: str | None
    related_sale_id: uuid.UUID | None
    created_at: datetime


class SendSaleNotificationRequest(BaseModel):
    channel: str = Field(default="sms", pattern="^(sms|whatsapp)$")

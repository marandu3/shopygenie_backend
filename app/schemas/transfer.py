import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.transfer import TransferStatus
from app.schemas.common import ORMModel


class TransferItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)


class TransferCreate(BaseModel):
    source_branch_id: uuid.UUID
    destination_branch_id: uuid.UUID
    note: str | None = None
    items: list[TransferItemIn] = Field(min_length=1)


class TransferItemOut(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int


class TransferOut(ORMModel):
    id: uuid.UUID
    source_branch_id: uuid.UUID
    destination_branch_id: uuid.UUID
    status: TransferStatus
    note: str | None
    requested_by: uuid.UUID
    approved_by: uuid.UUID | None
    received_by: uuid.UUID | None
    requested_at: datetime
    approved_at: datetime | None
    received_at: datetime | None
    items: list[TransferItemOut]

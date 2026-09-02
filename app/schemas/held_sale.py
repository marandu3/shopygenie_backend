import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class HeldSaleItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)
    discount_amount: float = Field(default=0, ge=0)


class HeldSaleCreate(BaseModel):
    customer_id: uuid.UUID | None = None
    register_id: uuid.UUID | None = None
    label: str | None = None
    items: list[HeldSaleItemIn]


class HeldSaleItemOut(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    discount_amount: float


class HeldSaleOut(ORMModel):
    id: uuid.UUID
    customer_id: uuid.UUID | None
    register_id: uuid.UUID | None
    label: str | None
    cashier_id: uuid.UUID
    created_at: datetime
    items: list[HeldSaleItemOut]

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class PurchaseItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)
    unit_cost_price: float = Field(gt=0)


class PurchaseCreate(BaseModel):
    supplier_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    items: list[PurchaseItemIn]

    @model_validator(mode="after")
    def validate_items(self):
        if not self.items:
            raise ValueError("A purchase must contain at least one item")
        return self


class PurchaseItemOut(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    quantity: int
    unit_cost_price: float
    line_total: float


class PurchaseOut(ORMModel):
    id: uuid.UUID
    purchase_number: str
    supplier_id: uuid.UUID | None
    purchased_by: uuid.UUID
    total_amount: float
    status: str
    items: list[PurchaseItemOut]
    created_at: datetime


class VoidPurchaseRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=300)

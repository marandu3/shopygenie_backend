import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class SaleReturnItemIn(BaseModel):
    sale_item_id: uuid.UUID
    quantity: int = Field(gt=0)


class SaleReturnCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=300)
    items: list[SaleReturnItemIn]

    @model_validator(mode="after")
    def validate_items(self):
        if not self.items:
            raise ValueError("A return must contain at least one item")
        return self


class SaleReturnItemOut(ORMModel):
    id: uuid.UUID
    sale_item_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    line_refund_amount: float


class SaleReturnOut(ORMModel):
    id: uuid.UUID
    sale_id: uuid.UUID
    reason: str
    refund_amount: float
    debt_reduction: float
    cash_refund_due: float
    items: list[SaleReturnItemOut]
    created_at: datetime


class PurchaseReturnItemIn(BaseModel):
    purchase_item_id: uuid.UUID
    quantity: int = Field(gt=0)


class PurchaseReturnCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=300)
    items: list[PurchaseReturnItemIn]

    @model_validator(mode="after")
    def validate_items(self):
        if not self.items:
            raise ValueError("A return must contain at least one item")
        return self


class PurchaseReturnItemOut(ORMModel):
    id: uuid.UUID
    purchase_item_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    line_refund_amount: float


class PurchaseReturnOut(ORMModel):
    id: uuid.UUID
    purchase_id: uuid.UUID
    reason: str
    refund_amount: float
    items: list[PurchaseReturnItemOut]
    created_at: datetime

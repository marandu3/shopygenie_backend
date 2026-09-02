import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class SaleItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)
    discount_amount: float = Field(default=0, ge=0)


class PaymentIn(BaseModel):
    amount: float = Field(gt=0)
    method: str  # CASH | CARD | MOBILE_MONEY | BANK | OTHER
    reference: str | None = None


class SaleCreate(BaseModel):
    customer_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    register_id: uuid.UUID | None = None
    items: list[SaleItemIn]
    payments: list[PaymentIn] = []
    allow_credit: bool = False  # if total exceeds payments, remainder becomes a Debt (requires customer_id)
    discount_approved_by: uuid.UUID | None = None  # required if discount % exceeds the org's auto-approve threshold
    credit_override_by: uuid.UUID | None = None  # required if this credit sale would exceed the customer's credit_limit
    notify_customer: bool = False  # cashier-selected: send a receipt SMS immediately (MASTER PROMPT §45)

    @model_validator(mode="after")
    def validate_items(self):
        if not self.items:
            raise ValueError("A sale must contain at least one item")
        return self


class SaleItemOut(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    quantity: int
    unit_selling_price: float
    unit_cost_price: float
    discount_amount: float
    line_total: float


class PaymentOut(ORMModel):
    id: uuid.UUID
    amount: float
    method: str
    reference: str | None
    created_at: datetime


class SaleOut(ORMModel):
    id: uuid.UUID
    sale_number: str
    customer_id: uuid.UUID | None
    cashier_id: uuid.UUID
    subtotal: float
    discount_total: float
    tax_total: float
    total_amount: float
    status: str
    items: list[SaleItemOut]
    payments: list[PaymentOut]
    created_at: datetime


class VoidSaleRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=300)

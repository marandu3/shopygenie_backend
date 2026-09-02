import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class DebtPaymentIn(BaseModel):
    amount: float = Field(gt=0)
    method: str = "CASH"
    reference: str | None = None


class DebtPaymentOut(ORMModel):
    id: uuid.UUID
    amount: float
    method: str
    reference: str | None
    created_at: datetime


class DebtOut(ORMModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    sale_id: uuid.UUID
    amount: float
    balance: float
    cleared: bool
    due_date: date | None
    payments: list[DebtPaymentOut] = []
    created_at: datetime

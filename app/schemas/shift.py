import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ShiftOpenRequest(BaseModel):
    register_id: uuid.UUID
    opening_cash: float = Field(ge=0)


class ShiftCloseRequest(BaseModel):
    actual_cash: float = Field(ge=0)
    closing_note: str | None = None


class CashMovementIn(BaseModel):
    movement_type: str  # CASH_IN | CASH_OUT
    amount: float = Field(gt=0)
    reason: str = Field(min_length=1, max_length=300)


class CashMovementOut(ORMModel):
    id: uuid.UUID
    movement_type: str
    amount: float
    reason: str
    performed_by: uuid.UUID
    created_at: datetime


class ShiftOut(ORMModel):
    id: uuid.UUID
    register_id: uuid.UUID
    cashier_id: uuid.UUID
    opening_cash: float
    opening_time: datetime
    actual_cash: float | None
    expected_cash: float | None
    variance: float | None
    closing_time: datetime | None
    closing_note: str | None
    status: str
    cash_movements: list[CashMovementOut] = []


class ShiftSnapshot(BaseModel):
    expected_cash: float

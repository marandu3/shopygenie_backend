import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ExpenseCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)


class ExpenseCategoryOut(ORMModel):
    id: uuid.UUID
    name: str
    is_active: bool


class ExpenseCreate(BaseModel):
    description: str = Field(min_length=1, max_length=300)
    amount: float = Field(gt=0)
    expense_date: date
    category_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None


class ExpenseUpdate(BaseModel):
    description: str | None = None
    amount: float | None = Field(default=None, gt=0)
    expense_date: date | None = None
    category_id: uuid.UUID | None = None


class ExpenseOut(ORMModel):
    id: uuid.UUID
    description: str
    amount: float
    expense_date: date
    category_id: uuid.UUID | None
    recorded_by: uuid.UUID
    is_approved: bool
    created_at: datetime

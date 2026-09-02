import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=30)
    email: str | None = None
    address: str | None = None
    credit_limit: float = Field(default=0, ge=0)


class CustomerUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    credit_limit: float | None = Field(default=None, ge=0)
    is_active: bool | None = None


class CustomerOut(ORMModel):
    id: uuid.UUID
    name: str
    phone: str
    email: str | None
    address: str | None
    credit_limit: float
    is_active: bool
    created_at: datetime
    # Computed, never stored — see app/models/customer.py docstring.
    outstanding_balance: float = 0


class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = None
    email: str | None = None
    address: str | None = None


class SupplierUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    is_active: bool | None = None


class SupplierOut(ORMModel):
    id: uuid.UUID
    name: str
    phone: str | None
    email: str | None
    address: str | None
    is_active: bool
    created_at: datetime

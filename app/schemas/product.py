import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)


class CategoryOut(ORMModel):
    id: uuid.UUID
    name: str
    is_active: bool


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sku: str | None = None
    barcode: str | None = None
    unit: str = "pcs"
    category_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    cost_price: float = Field(ge=0)
    selling_price: float = Field(ge=0)
    current_stock: int = Field(default=0, ge=0)
    low_stock_alert: int | None = Field(default=None, ge=0)


class ProductUpdate(BaseModel):
    name: str | None = None
    sku: str | None = None
    barcode: str | None = None
    unit: str | None = None
    category_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    cost_price: float | None = Field(default=None, ge=0)
    selling_price: float | None = Field(default=None, ge=0)
    low_stock_alert: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ProductOut(ORMModel):
    id: uuid.UUID
    name: str
    sku: str | None
    barcode: str | None
    unit: str
    category_id: uuid.UUID | None
    supplier_id: uuid.UUID | None
    cost_price: float
    selling_price: float
    current_stock: int
    low_stock_alert: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class StockLevelOut(BaseModel):
    id: uuid.UUID
    name: str
    current_stock: int
    low_stock_alert: int | None


class StockValuationLine(BaseModel):
    id: uuid.UUID
    name: str
    current_stock: int
    cost_price: float
    valuation: float


class StockValuationOut(BaseModel):
    total_valuation: float
    lines: list[StockValuationLine]


class InventoryAdjustmentRequest(BaseModel):
    quantity_delta: int  # positive = add stock, negative = remove stock
    reason: str = Field(min_length=1, max_length=300)

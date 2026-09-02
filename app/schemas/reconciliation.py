import uuid
from datetime import datetime

from pydantic import BaseModel


class InventoryReconciliationLine(BaseModel):
    product_id: uuid.UUID
    product_name: str
    ledger_computed_stock: int
    cached_current_stock: int
    discrepancy: int  # cached - ledger; should always be 0 by construction


class InventoryReconciliationReport(BaseModel):
    lines: list[InventoryReconciliationLine]
    discrepancy_count: int
    generated_at: datetime


class CashReconciliationLine(BaseModel):
    shift_id: uuid.UUID
    register_id: uuid.UUID
    cashier_id: uuid.UUID
    opening_cash: float
    expected_cash: float | None
    actual_cash: float | None
    variance: float | None
    opening_time: datetime
    closing_time: datetime | None


class CashReconciliationReport(BaseModel):
    lines: list[CashReconciliationLine]
    total_variance: float
    generated_at: datetime

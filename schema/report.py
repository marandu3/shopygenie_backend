from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from enum import Enum

class ReportType(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    CUSTOM = "custom"

class ReportSummary(BaseModel):
    total_sales: float
    total_purchases: float
    total_debts: float
    total_expenditures: float
    net_profit: float
    most_sold_product: Optional[str] = None
    least_sold_product: Optional[str] = None
    best_customer: Optional[str] = None
    worst_customer: Optional[str] = None
    ReportType: ReportType
    generated_at: datetime = datetime.now(timezone.utc)

class ReportFilters(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    category: Optional[str] = None
    customer_id: Optional[str] = None
    product_id: Optional[int] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
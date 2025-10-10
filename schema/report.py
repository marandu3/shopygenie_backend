from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum

class ReportType(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    CUSTOM = "custom"

class ReportSummary(BaseModel):
    # Basic financial metrics
    total_sales: float = 0.0
    total_purchases: float = 0.0
    total_debts: float = 0.0
    total_expenditures: float = 0.0
    net_profit: float = 0.0
    
    # Product metrics
    most_sold_product: Optional[str] = None
    least_sold_product: Optional[str] = None
    total_products_sold: int = 0
    
    # Customer metrics
    best_customer: Optional[str] = None
    worst_customer: Optional[str] = None
    total_customers: int = 0
    
    # Additional metrics
    average_sale_amount: float = 0.0
    total_transactions: int = 0
    
    # Report metadata
    report_type: ReportType
    report_title: str = "General Business Report"
    generated_at: datetime = datetime.now(timezone.utc)
    
    # Filter information
    applied_filters: Dict[str, Any] = {}

class ReportFilters(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    category: Optional[str] = None
    customer_id: Optional[str] = None
    product_id: Optional[int] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
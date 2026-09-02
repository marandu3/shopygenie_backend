import uuid
from datetime import datetime

from pydantic import BaseModel


class ReportFilters(BaseModel):
    start_date: datetime | None = None
    end_date: datetime | None = None
    branch_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None


class BusinessSummaryReport(BaseModel):
    """Correct accounting model — see app/services/reports.py.

    revenue        = sum of completed sale totals
    cogs            = sum of (unit_cost_price x quantity) for items in completed sales
    gross_profit    = revenue - cogs
    gross_margin_pct = gross_profit / revenue * 100
    operating_expenses = sum of Expense records ONLY (not purchases, not debts)
    net_profit      = gross_profit - operating_expenses
    outstanding_receivables = sum of uncleared Debt balances (NOT an expense)
    """

    revenue: float = 0
    cogs: float = 0
    gross_profit: float = 0
    gross_margin_percent: float = 0
    operating_expenses: float = 0
    net_profit: float = 0
    net_margin_percent: float = 0

    total_purchases: float = 0
    outstanding_receivables: float = 0

    total_transactions: int = 0
    average_sale_amount: float = 0
    total_units_sold: int = 0

    most_sold_product: str | None = None
    least_sold_product: str | None = None
    top_spending_customer: str | None = None
    lowest_spending_customer: str | None = None

    generated_at: datetime

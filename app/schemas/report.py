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


class PaymentMethodTotal(BaseModel):
    method: str
    total: float


class SalesReport(BaseModel):
    gross_sales: float = 0  # subtotal before discounts, across completed sales
    discounts: float = 0
    tax: float = 0
    net_sales: float = 0  # == revenue in BusinessSummaryReport
    refund_amount: float = 0
    transactions: int = 0
    units_sold: int = 0
    average_transaction: float = 0
    payment_breakdown: list[PaymentMethodTotal] = []
    generated_at: datetime


class ProductMovementSummary(BaseModel):
    product_id: uuid.UUID
    product_name: str
    units_sold: int
    revenue: float


class InventoryReport(BaseModel):
    total_stock_value: float = 0
    low_stock_count: int = 0
    out_of_stock_count: int = 0
    fast_movers: list[ProductMovementSummary] = []
    slow_movers: list[ProductMovementSummary] = []  # includes zero-movement products
    generated_at: datetime


class CustomerSpend(BaseModel):
    customer_id: uuid.UUID
    customer_name: str
    total_spent: float
    transactions: int


class CustomerReport(BaseModel):
    total_customers: int = 0
    new_customers: int = 0  # created within the filter window
    top_customers: list[CustomerSpend] = []
    total_outstanding_receivables: float = 0
    generated_at: datetime


class SupplierPurchaseSummary(BaseModel):
    supplier_id: uuid.UUID | None
    supplier_name: str
    total_purchased: float
    purchase_count: int


class SupplierReport(BaseModel):
    suppliers: list[SupplierPurchaseSummary] = []
    generated_at: datetime


class DebtAgingBucket(BaseModel):
    label: str
    count: int
    amount: float


class DebtAgingReport(BaseModel):
    buckets: list[DebtAgingBucket] = []
    total_outstanding: float = 0
    generated_at: datetime

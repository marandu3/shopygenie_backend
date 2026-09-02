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


class ComparisonRequest(BaseModel):
    start_date: datetime
    end_date: datetime


class ComparisonMetric(BaseModel):
    label: str
    current: float
    previous: float
    # Deliberately nullable: a percent change against a zero baseline is
    # meaningless/misleading (MASTER PROMPT §48) — omit it, don't show "+inf%".
    change_percent: float | None = None


class ComparisonReport(BaseModel):
    current_start: datetime
    current_end: datetime
    previous_start: datetime
    previous_end: datetime
    metrics: list[ComparisonMetric]
    generated_at: datetime


class TimeSeriesRequest(BaseModel):
    start_date: datetime
    end_date: datetime
    metric: str = "revenue"  # revenue | transactions | profit


class TimeSeriesPoint(BaseModel):
    date: str
    value: float


class TimeSeriesReport(BaseModel):
    metric: str
    points: list[TimeSeriesPoint]
    generated_at: datetime


class HeatmapCell(BaseModel):
    day_of_week: int  # 0=Monday .. 6=Sunday
    hour: int  # 0-23
    revenue: float
    transactions: int


class HeatmapReport(BaseModel):
    cells: list[HeatmapCell]
    generated_at: datetime


class ParetoLine(BaseModel):
    product_id: uuid.UUID
    product_name: str
    revenue: float
    cumulative_percent: float
    in_top_80_percent: bool


class ParetoReport(BaseModel):
    lines: list[ParetoLine]
    generated_at: datetime


class SalesPowerPoint(BaseModel):
    timestamp: datetime
    value: float


class SalesPowerReport(BaseModel):
    """MASTER PROMPT §54 — a real scatter dataset plus analytical
    interpretation, not a decorative chart."""

    points: list[SalesPowerPoint]
    trend_start_value: float | None
    trend_end_value: float | None
    trend_direction: str  # "growing" | "declining" | "flat" | "insufficient_data"
    peak_value: float | None
    peak_timestamp: datetime | None
    weakest_value: float | None
    weakest_timestamp: datetime | None
    volatility: float  # standard deviation of individual sale values
    growth_percent: float | None  # second half of the period vs first half

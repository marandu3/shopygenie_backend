from pydantic import BaseModel, Field

from app.schemas.report import ReportFilters

ALLOWED_METRICS = {"revenue", "gross_profit", "cogs", "transactions", "units_sold"}
ALLOWED_GROUP_BY = {None, "product", "customer", "day", "month"}


class ReportBuilderRequest(BaseModel):
    metric: str = Field(description="revenue | gross_profit | cogs | transactions | units_sold")
    group_by: str | None = Field(default=None, description="product | customer | day | month | null for a single total")
    filters: ReportFilters = ReportFilters()
    compare_previous: bool = False


class ReportBuilderRow(BaseModel):
    label: str
    value: float
    compare_value: float | None = None
    change_percent: float | None = None


class ReportBuilderResult(BaseModel):
    metric: str
    group_by: str | None
    rows: list[ReportBuilderRow]
    total: float

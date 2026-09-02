from pydantic import BaseModel


class UsageMetricOut(BaseModel):
    metric: str
    period: str
    count: int


class QuotaOut(BaseModel):
    used: int
    quota: int | None  # None = unlimited
    remaining: int | None
    percentage: float | None
    exhausted: bool
    warning: bool


class UsageSummaryOut(BaseModel):
    period: str
    metrics: list[UsageMetricOut]
    whatsapp: QuotaOut
    storage_bytes: QuotaOut


class OrgLimitsOut(BaseModel):
    """MASTER PROMPT §67 — feature entitlements shown alongside the current
    plan so a locked action can explain itself instead of just failing."""

    plan_display_name: str | None
    branches: QuotaOut
    workers: QuotaOut

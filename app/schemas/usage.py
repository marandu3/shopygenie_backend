from pydantic import BaseModel


class UsageMetricOut(BaseModel):
    metric: str
    period: str
    count: int


class UsageSummaryOut(BaseModel):
    period: str
    metrics: list[UsageMetricOut]

from pydantic import BaseModel, Field

ALLOWED_PLATFORM_METRICS = {
    "organizations_by_month",
    "subscription_distribution",
    "sms_activity_by_month",
    "whatsapp_usage_by_plan",
    "storage_consumption_by_plan",
}


class PlatformReportBuilderRequest(BaseModel):
    metric: str = Field(
        description="organizations_by_month | subscription_distribution | sms_activity_by_month | "
        "whatsapp_usage_by_plan | storage_consumption_by_plan"
    )


class PlatformReportBuilderRow(BaseModel):
    label: str
    value: float


class PlatformReportBuilderResult(BaseModel):
    metric: str
    rows: list[PlatformReportBuilderRow]
    total: float

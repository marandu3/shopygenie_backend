from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission
from app.core.permissions import REPORTS_VIEW
from app.db.session import get_db
from app.schemas.report import (
    BusinessSummaryReport,
    ComparisonReport,
    ComparisonRequest,
    CustomerReport,
    DebtAgingReport,
    HeatmapReport,
    InventoryReport,
    ParetoReport,
    ReportFilters,
    SalesReport,
    SupplierReport,
    TimeSeriesReport,
    TimeSeriesRequest,
)
from app.services.reports import (
    build_business_summary,
    build_comparison_report,
    build_customer_report,
    build_debt_aging_report,
    build_heatmap_report,
    build_inventory_report,
    build_pareto_report,
    build_sales_report,
    build_supplier_report,
    build_timeseries_report,
)

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post("/summary", response_model=BusinessSummaryReport)
async def business_summary(
    filters: ReportFilters = ReportFilters(),
    ctx: AuthContext = Depends(require_permission(REPORTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    return await build_business_summary(db, organization_id=org_id, filters=filters)


@router.post("/sales", response_model=SalesReport)
async def sales_report(
    filters: ReportFilters = ReportFilters(),
    ctx: AuthContext = Depends(require_permission(REPORTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    return await build_sales_report(db, organization_id=org_id, filters=filters)


@router.post("/inventory", response_model=InventoryReport)
async def inventory_report(
    filters: ReportFilters = ReportFilters(),
    ctx: AuthContext = Depends(require_permission(REPORTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    return await build_inventory_report(db, organization_id=org_id, filters=filters)


@router.post("/customers", response_model=CustomerReport)
async def customer_report(
    filters: ReportFilters = ReportFilters(),
    ctx: AuthContext = Depends(require_permission(REPORTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    return await build_customer_report(db, organization_id=org_id, filters=filters)


@router.post("/suppliers", response_model=SupplierReport)
async def supplier_report(
    filters: ReportFilters = ReportFilters(),
    ctx: AuthContext = Depends(require_permission(REPORTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    return await build_supplier_report(db, organization_id=org_id, filters=filters)


@router.post("/debts/aging", response_model=DebtAgingReport)
async def debt_aging_report(
    filters: ReportFilters = ReportFilters(),
    ctx: AuthContext = Depends(require_permission(REPORTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    return await build_debt_aging_report(db, organization_id=org_id, filters=filters)


@router.post("/comparison", response_model=ComparisonReport)
async def comparison_report(
    payload: ComparisonRequest,
    ctx: AuthContext = Depends(require_permission(REPORTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    return await build_comparison_report(db, organization_id=org_id, current_start=payload.start_date, current_end=payload.end_date)


@router.post("/timeseries", response_model=TimeSeriesReport)
async def timeseries_report(
    payload: TimeSeriesRequest,
    ctx: AuthContext = Depends(require_permission(REPORTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    return await build_timeseries_report(db, organization_id=org_id, start=payload.start_date, end=payload.end_date, metric=payload.metric)


@router.get("/heatmap", response_model=HeatmapReport)
async def heatmap_report(
    ctx: AuthContext = Depends(require_permission(REPORTS_VIEW)),
    db: AsyncSession = Depends(get_db),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
):
    org_id = ctx.require_organization_id()
    return await build_heatmap_report(db, organization_id=org_id, start=start_date, end=end_date)


@router.post("/pareto", response_model=ParetoReport)
async def pareto_report(
    filters: ReportFilters = ReportFilters(),
    ctx: AuthContext = Depends(require_permission(REPORTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    return await build_pareto_report(db, organization_id=org_id, filters=filters)

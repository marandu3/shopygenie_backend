from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission
from app.core.permissions import REPORTS_VIEW
from app.db.session import get_db
from app.schemas.report import BusinessSummaryReport, ReportFilters
from app.services.reports import build_business_summary

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post("/summary", response_model=BusinessSummaryReport)
async def business_summary(
    filters: ReportFilters = ReportFilters(),
    ctx: AuthContext = Depends(require_permission(REPORTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    return await build_business_summary(db, organization_id=org_id, filters=filters)

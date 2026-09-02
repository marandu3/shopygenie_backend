from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission
from app.core.permissions import RECONCILIATION_VIEW
from app.db.session import get_db
from app.schemas.reconciliation import CashReconciliationReport, InventoryReconciliationReport
from app.services.reconciliation import build_cash_reconciliation, build_inventory_reconciliation

router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])


@router.get("/inventory", response_model=InventoryReconciliationReport)
async def inventory_reconciliation(
    ctx: AuthContext = Depends(require_permission(RECONCILIATION_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    return await build_inventory_reconciliation(db, organization_id=org_id)


@router.get("/cash", response_model=CashReconciliationReport)
async def cash_reconciliation(
    ctx: AuthContext = Depends(require_permission(RECONCILIATION_VIEW)),
    db: AsyncSession = Depends(get_db),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
):
    org_id = ctx.require_organization_id()
    return await build_cash_reconciliation(db, organization_id=org_id, start_date=start_date, end_date=end_date)

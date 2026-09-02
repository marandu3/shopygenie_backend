import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryMovement
from app.models.product import Product
from app.models.shift import Shift, ShiftStatus
from app.schemas.reconciliation import (
    CashReconciliationLine,
    CashReconciliationReport,
    InventoryReconciliationLine,
    InventoryReconciliationReport,
)


async def build_inventory_reconciliation(db: AsyncSession, *, organization_id: uuid.UUID) -> InventoryReconciliationReport:
    """Proves (or disproves) that the cached Product.current_stock still
    matches SUM(InventoryMovement.quantity) — the append-only ledger is the
    audit source of truth; this report is what would catch the cache ever
    drifting from it (a bug elsewhere, a manual DB edit, etc.)."""
    ledger_result = await db.execute(
        select(InventoryMovement.product_id, func.coalesce(func.sum(InventoryMovement.quantity), 0))
        .where(InventoryMovement.organization_id == organization_id)
        .group_by(InventoryMovement.product_id)
    )
    ledger_totals = {row[0]: int(row[1]) for row in ledger_result.all()}

    products_result = await db.execute(
        select(Product.id, Product.name, Product.current_stock).where(Product.organization_id == organization_id)
    )

    lines: list[InventoryReconciliationLine] = []
    for product_id, name, current_stock in products_result.all():
        ledger_stock = ledger_totals.get(product_id, 0)
        lines.append(
            InventoryReconciliationLine(
                product_id=product_id,
                product_name=name,
                ledger_computed_stock=ledger_stock,
                cached_current_stock=current_stock,
                discrepancy=current_stock - ledger_stock,
            )
        )

    return InventoryReconciliationReport(
        lines=lines,
        discrepancy_count=sum(1 for line in lines if line.discrepancy != 0),
        generated_at=datetime.now(timezone.utc),
    )


async def build_cash_reconciliation(
    db: AsyncSession, *, organization_id: uuid.UUID, start_date: datetime | None, end_date: datetime | None
) -> CashReconciliationReport:
    conditions = [Shift.organization_id == organization_id, Shift.status == ShiftStatus.CLOSED]
    if start_date:
        conditions.append(Shift.closing_time >= start_date)
    if end_date:
        conditions.append(Shift.closing_time <= end_date)

    result = await db.execute(select(Shift).where(*conditions).order_by(Shift.closing_time.desc()))
    shifts = list(result.scalars())

    lines = [
        CashReconciliationLine(
            shift_id=s.id,
            register_id=s.register_id,
            cashier_id=s.cashier_id,
            opening_cash=float(s.opening_cash),
            expected_cash=float(s.expected_cash) if s.expected_cash is not None else None,
            actual_cash=float(s.actual_cash) if s.actual_cash is not None else None,
            variance=float(s.variance) if s.variance is not None else None,
            opening_time=s.opening_time,
            closing_time=s.closing_time,
        )
        for s in shifts
    ]

    total_variance = sum(line.variance or 0 for line in lines)

    return CashReconciliationReport(lines=lines, total_variance=round(total_variance, 2), generated_at=datetime.now(timezone.utc))

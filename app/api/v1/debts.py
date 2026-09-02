import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import AuthContext, require_permission
from app.core.permissions import DEBTS_COLLECT, DEBTS_VIEW
from app.db.session import get_db
from app.models.debt import Debt
from app.schemas.debt import DebtOut, DebtPaymentIn
from app.services.debts import pay_debt

router = APIRouter(prefix="/debts", tags=["Debts"])


@router.get("", response_model=list[DebtOut])
async def list_debts(
    ctx: AuthContext = Depends(require_permission(DEBTS_VIEW)),
    db: AsyncSession = Depends(get_db),
    customer_id: uuid.UUID | None = None,
    unpaid_only: bool = False,
):
    org_id = ctx.require_organization_id()
    conditions = [Debt.organization_id == org_id]
    if customer_id:
        conditions.append(Debt.customer_id == customer_id)
    if unpaid_only:
        conditions.append(Debt.cleared.is_(False))

    result = await db.execute(
        select(Debt).where(*conditions).options(selectinload(Debt.payments)).order_by(Debt.created_at.desc())
    )
    return list(result.scalars())


@router.post("/{debt_id}/pay", response_model=DebtOut)
async def pay_debt_endpoint(
    debt_id: uuid.UUID,
    payload: DebtPaymentIn,
    ctx: AuthContext = Depends(require_permission(DEBTS_COLLECT)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    debt = await pay_debt(
        db,
        organization_id=org_id,
        debt_id=debt_id,
        amount=Decimal(str(payload.amount)),
        method=payload.method,
        reference=payload.reference,
        received_by=ctx.user_id,
    )
    await db.commit()
    await db.refresh(debt, attribute_names=["payments"])
    return debt

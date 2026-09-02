import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import AuthContext, require_permission
from app.core.permissions import DEBTS_COLLECT, DEBTS_VIEW
from app.db.session import get_db
from app.models.billing import SmsMessageType
from app.models.customer import Customer
from app.models.debt import Debt
from app.models.organization import Organization
from app.schemas.debt import (
    DebtOut,
    DebtPaymentIn,
    DebtReminderResult,
    SendDebtRemindersRequest,
    SendDebtRemindersResponse,
)
from app.services.debts import pay_debt
from app.services.notifications import send_sms

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


@router.post("/send-reminders", response_model=SendDebtRemindersResponse)
async def send_debt_reminders(
    payload: SendDebtRemindersRequest,
    ctx: AuthContext = Depends(require_permission(DEBTS_COLLECT)),
    db: AsyncSession = Depends(get_db),
):
    """Bulk SMS reminder run (MASTER PROMPT §46 outbound-progress use case).
    Sends inline, one at a time, and returns per-recipient results so the
    frontend can render a genuine sent/total progress bar from the response
    rather than a decorative animation."""
    org_id = ctx.require_organization_id()
    org = await db.get(Organization, org_id)

    conditions = [Debt.organization_id == org_id, Debt.cleared.is_(False)]
    if payload.debt_ids:
        conditions.append(Debt.id.in_(payload.debt_ids))
    result = await db.execute(select(Debt).where(*conditions))
    debts = list(result.scalars())

    results: list[DebtReminderResult] = []
    for debt in debts:
        customer = await db.get(Customer, debt.customer_id)
        if customer is None or not customer.phone:
            results.append(
                DebtReminderResult(debt_id=debt.id, customer_name=customer.name if customer else "?", recipient=None, sent=False, error="No phone on file")
            )
            continue

        message = (
            f"{org.name}: Dear {customer.name}, you have an outstanding balance of "
            f"{org.currency} {debt.balance}. Please settle at your earliest convenience."
        )
        try:
            log = await send_sms(
                organization_id=org_id,
                to=customer.phone,
                message=message,
                message_type=SmsMessageType.DEBT_REMINDER,
                sent_by=ctx.user_id,
            )
            results.append(
                DebtReminderResult(debt_id=debt.id, customer_name=customer.name, recipient=customer.phone, sent=(log.status.value == "SENT"), error=log.error)
            )
        except Exception as exc:  # noqa: BLE001 — one recipient's failure must not abort the batch
            results.append(DebtReminderResult(debt_id=debt.id, customer_name=customer.name, recipient=customer.phone, sent=False, error=str(exc)))

    sent_count = sum(1 for r in results if r.sent)
    return SendDebtRemindersResponse(total=len(results), sent=sent_count, failed=len(results) - sent_count, results=results)

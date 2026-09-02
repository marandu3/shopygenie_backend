import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.debt import Debt, DebtPayment
from app.models.sale import PaymentMethod
from app.services.money import money


async def customer_outstanding_balance(db: AsyncSession, *, organization_id: uuid.UUID, customer_id: uuid.UUID) -> Decimal:
    """The ONLY correct way to know what a customer owes — never a stored,
    overwritable field (see app/models/customer.py)."""
    result = await db.execute(
        select(func.coalesce(func.sum(Debt.balance), 0)).where(
            Debt.organization_id == organization_id,
            Debt.customer_id == customer_id,
            Debt.cleared.is_(False),
        )
    )
    return money(result.scalar_one())


async def outstanding_balances_for_customers(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    if not customer_ids:
        return {}
    result = await db.execute(
        select(Debt.customer_id, func.coalesce(func.sum(Debt.balance), 0))
        .where(
            Debt.organization_id == organization_id,
            Debt.customer_id.in_(customer_ids),
            Debt.cleared.is_(False),
        )
        .group_by(Debt.customer_id)
    )
    return {row[0]: money(row[1]) for row in result.all()}


async def pay_debt(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    debt_id: uuid.UUID,
    amount: Decimal,
    method: str,
    reference: str | None,
    received_by: uuid.UUID,
) -> Debt:
    result = await db.execute(
        select(Debt)
        .where(Debt.id == debt_id, Debt.organization_id == organization_id)
        .with_for_update()
    )
    debt = result.scalar_one_or_none()
    if debt is None:
        raise NotFoundError("Debt not found")
    if debt.cleared:
        raise ValidationAppError("This debt is already fully paid", code="DEBT_ALREADY_CLEARED")

    amount = money(amount)
    if amount <= 0:
        raise ValidationAppError("Payment amount must be greater than zero", code="INVALID_AMOUNT")
    if amount > debt.balance:
        raise ValidationAppError(
            f"Payment ({amount}) exceeds this debt's remaining balance ({debt.balance})",
            code="OVERPAYMENT",
        )

    try:
        payment_method = PaymentMethod(method)
    except ValueError:
        raise ValidationAppError(f"Unknown payment method: {method}", code="INVALID_PAYMENT_METHOD")

    # This ONLY ever touches this one debt row — it never writes to any
    # customer-level aggregate. That aggregate is always derived (see above).
    debt.balance = money(debt.balance - amount)
    debt.cleared = debt.balance == 0

    db.add(
        DebtPayment(
            debt_id=debt.id,
            received_by=received_by,
            amount=amount,
            method=payment_method,
            reference=reference,
            created_at=datetime.now(timezone.utc),
        )
    )

    await db.flush()
    return debt

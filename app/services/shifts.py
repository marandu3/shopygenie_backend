import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.sale import Payment, PaymentMethod, Sale
from app.models.shift import CashMovement, CashMovementType, Shift, ShiftStatus
from app.services.money import money


async def get_open_shift(db: AsyncSession, *, organization_id: uuid.UUID, register_id: uuid.UUID) -> Shift | None:
    result = await db.execute(
        select(Shift).where(
            Shift.organization_id == organization_id,
            Shift.register_id == register_id,
            Shift.status == ShiftStatus.OPEN,
        )
    )
    return result.scalar_one_or_none()


async def open_shift(
    db: AsyncSession, *, organization_id: uuid.UUID, register_id: uuid.UUID, cashier_id: uuid.UUID, opening_cash: Decimal
) -> Shift:
    existing = await get_open_shift(db, organization_id=organization_id, register_id=register_id)
    if existing is not None:
        raise ValidationAppError("This register already has an open shift", code="SHIFT_ALREADY_OPEN")

    shift = Shift(
        organization_id=organization_id,
        register_id=register_id,
        cashier_id=cashier_id,
        opening_cash=money(opening_cash),
        opening_time=datetime.now(timezone.utc),
        status=ShiftStatus.OPEN,
    )
    db.add(shift)
    await db.flush()
    return shift


async def _compute_expected_cash(db: AsyncSession, shift: Shift) -> Decimal:
    window_end = shift.closing_time or datetime.now(timezone.utc)

    cash_sales_result = await db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .select_from(Payment)
        .join(Sale, Sale.id == Payment.sale_id)
        .where(
            Sale.register_id == shift.register_id,
            Payment.method == PaymentMethod.CASH,
            Payment.created_at >= shift.opening_time,
            Payment.created_at <= window_end,
        )
    )
    cash_sales = money(cash_sales_result.scalar_one())

    cash_in_result = await db.execute(
        select(func.coalesce(func.sum(CashMovement.amount), 0)).where(
            CashMovement.shift_id == shift.id, CashMovement.movement_type == CashMovementType.CASH_IN
        )
    )
    cash_out_result = await db.execute(
        select(func.coalesce(func.sum(CashMovement.amount), 0)).where(
            CashMovement.shift_id == shift.id, CashMovement.movement_type == CashMovementType.CASH_OUT
        )
    )
    cash_in = money(cash_in_result.scalar_one())
    cash_out = money(cash_out_result.scalar_one())

    return money(shift.opening_cash + cash_sales + cash_in - cash_out)


async def close_shift(
    db: AsyncSession, *, organization_id: uuid.UUID, shift_id: uuid.UUID, actual_cash: Decimal, closing_note: str | None
) -> Shift:
    shift = await db.get(Shift, shift_id)
    if shift is None or shift.organization_id != organization_id:
        raise NotFoundError("Shift not found")
    if shift.status == ShiftStatus.CLOSED:
        raise ValidationAppError("Shift is already closed", code="SHIFT_ALREADY_CLOSED")

    shift.closing_time = datetime.now(timezone.utc)
    expected = await _compute_expected_cash(db, shift)
    shift.expected_cash = expected
    shift.actual_cash = money(actual_cash)
    shift.variance = money(shift.actual_cash - expected)
    shift.closing_note = closing_note
    shift.status = ShiftStatus.CLOSED

    await db.flush()
    return shift


async def add_cash_movement(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    shift_id: uuid.UUID,
    movement_type: CashMovementType,
    amount: Decimal,
    reason: str,
    performed_by: uuid.UUID,
) -> CashMovement:
    shift = await db.get(Shift, shift_id)
    if shift is None or shift.organization_id != organization_id:
        raise NotFoundError("Shift not found")
    if shift.status != ShiftStatus.OPEN:
        raise ValidationAppError("Cannot record cash movements on a closed shift", code="SHIFT_CLOSED")

    amount = money(amount)
    if amount <= 0:
        raise ValidationAppError("Amount must be greater than zero", code="INVALID_AMOUNT")

    movement = CashMovement(
        shift_id=shift.id,
        performed_by=performed_by,
        movement_type=movement_type,
        amount=amount,
        reason=reason,
        created_at=datetime.now(timezone.utc),
    )
    db.add(movement)
    await db.flush()
    return movement


async def shift_snapshot(db: AsyncSession, shift: Shift) -> dict:
    """Live expected-cash preview for an OPEN shift (no side effects)."""
    expected = await _compute_expected_cash(db, shift)
    return {"expected_cash": expected}

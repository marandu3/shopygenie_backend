import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import AuthContext, require_permission
from app.core.exceptions import NotFoundError, ValidationAppError
from app.core.permissions import SHIFTS_OPEN, SHIFTS_VIEW
from app.db.session import get_db
from app.models.shift import CashMovement, CashMovementType, Shift
from app.schemas.shift import CashMovementIn, ShiftCloseRequest, ShiftOpenRequest, ShiftOut, ShiftSnapshot
from app.services.shifts import add_cash_movement, close_shift, get_open_shift, open_shift, shift_snapshot

router = APIRouter(prefix="/shifts", tags=["Shifts"])


@router.post("/open", response_model=ShiftOut, status_code=201)
async def open_shift_endpoint(
    payload: ShiftOpenRequest,
    ctx: AuthContext = Depends(require_permission(SHIFTS_OPEN)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    shift = await open_shift(
        db, organization_id=org_id, register_id=payload.register_id, cashier_id=ctx.user_id, opening_cash=Decimal(str(payload.opening_cash))
    )
    await db.commit()
    result = await db.execute(select(Shift).where(Shift.id == shift.id).options(selectinload(Shift.cash_movements)))
    return result.scalar_one()
    return shift


@router.get("/current", response_model=ShiftOut | None)
async def current_shift(
    register_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission(SHIFTS_OPEN)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    shift = await get_open_shift(db, organization_id=org_id, register_id=register_id)
    if shift is None:
        return None
    result = await db.execute(select(Shift).where(Shift.id == shift.id).options(selectinload(Shift.cash_movements)))
    return result.scalar_one()


@router.get("/{shift_id}", response_model=ShiftOut)
async def get_shift(
    shift_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission(SHIFTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    result = await db.execute(
        select(Shift).where(Shift.id == shift_id, Shift.organization_id == org_id).options(selectinload(Shift.cash_movements))
    )
    shift = result.scalar_one_or_none()
    if shift is None:
        raise NotFoundError("Shift not found")
    return shift


@router.get("/{shift_id}/snapshot", response_model=ShiftSnapshot)
async def get_shift_snapshot(
    shift_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission(SHIFTS_OPEN)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    shift = await db.get(Shift, shift_id)
    if shift is None or shift.organization_id != org_id:
        raise NotFoundError("Shift not found")
    snap = await shift_snapshot(db, shift)
    return ShiftSnapshot(expected_cash=float(snap["expected_cash"]))


@router.get("", response_model=list[ShiftOut])
async def list_shifts(
    ctx: AuthContext = Depends(require_permission(SHIFTS_VIEW)),
    db: AsyncSession = Depends(get_db),
    register_id: uuid.UUID | None = None,
):
    org_id = ctx.require_organization_id()
    conditions = [Shift.organization_id == org_id]
    if register_id:
        conditions.append(Shift.register_id == register_id)
    result = await db.execute(
        select(Shift).where(*conditions).options(selectinload(Shift.cash_movements)).order_by(Shift.opening_time.desc())
    )
    return list(result.scalars())


@router.post("/{shift_id}/close", response_model=ShiftOut)
async def close_shift_endpoint(
    shift_id: uuid.UUID,
    payload: ShiftCloseRequest,
    ctx: AuthContext = Depends(require_permission(SHIFTS_OPEN)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    shift = await close_shift(
        db, organization_id=org_id, shift_id=shift_id, actual_cash=Decimal(str(payload.actual_cash)), closing_note=payload.closing_note
    )
    await db.commit()
    result = await db.execute(select(Shift).where(Shift.id == shift.id).options(selectinload(Shift.cash_movements)))
    return result.scalar_one()


@router.post("/{shift_id}/cash-movement", response_model=ShiftOut)
async def add_cash_movement_endpoint(
    shift_id: uuid.UUID,
    payload: CashMovementIn,
    ctx: AuthContext = Depends(require_permission(SHIFTS_OPEN)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    try:
        movement_type = CashMovementType(payload.movement_type)
    except ValueError:
        raise ValidationAppError(f"Unknown movement type: {payload.movement_type}", code="INVALID_MOVEMENT_TYPE")

    await add_cash_movement(
        db,
        organization_id=org_id,
        shift_id=shift_id,
        movement_type=movement_type,
        amount=Decimal(str(payload.amount)),
        reason=payload.reason,
        performed_by=ctx.user_id,
    )
    await db.commit()
    result = await db.execute(select(Shift).where(Shift.id == shift_id).options(selectinload(Shift.cash_movements)))
    return result.scalar_one()

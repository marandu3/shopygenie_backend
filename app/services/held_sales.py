import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.held_sale import HeldSale, HeldSaleItem
from app.schemas.held_sale import HeldSaleCreate


async def create_held_sale(
    db: AsyncSession, *, organization_id: uuid.UUID, cashier_id: uuid.UUID, payload: HeldSaleCreate
) -> HeldSale:
    held = HeldSale(
        organization_id=organization_id,
        register_id=payload.register_id,
        customer_id=payload.customer_id,
        cashier_id=cashier_id,
        label=payload.label,
        created_at=datetime.now(timezone.utc),
        items=[
            HeldSaleItem(product_id=i.product_id, quantity=i.quantity, discount_amount=i.discount_amount)
            for i in payload.items
        ],
    )
    db.add(held)
    await db.flush()
    result = await db.execute(select(HeldSale).where(HeldSale.id == held.id).options(selectinload(HeldSale.items)))
    return result.scalar_one()


async def list_held_sales(db: AsyncSession, *, organization_id: uuid.UUID) -> list[HeldSale]:
    result = await db.execute(
        select(HeldSale)
        .where(HeldSale.organization_id == organization_id)
        .options(selectinload(HeldSale.items))
        .order_by(HeldSale.created_at.desc())
    )
    return list(result.scalars())


async def get_held_sale(db: AsyncSession, *, organization_id: uuid.UUID, held_sale_id: uuid.UUID) -> HeldSale:
    result = await db.execute(
        select(HeldSale)
        .where(HeldSale.id == held_sale_id, HeldSale.organization_id == organization_id)
        .options(selectinload(HeldSale.items))
    )
    held = result.scalar_one_or_none()
    if held is None:
        raise NotFoundError("Held sale not found")
    return held


async def discard_held_sale(db: AsyncSession, *, organization_id: uuid.UUID, held_sale_id: uuid.UUID) -> None:
    held = await get_held_sale(db, organization_id=organization_id, held_sale_id=held_sale_id)
    await db.delete(held)
    await db.flush()

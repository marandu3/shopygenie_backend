import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import CostLayerSource, InventoryCostLayer
from app.services.money import money


async def add_cost_layer(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    product_id: uuid.UUID,
    source_type: CostLayerSource,
    source_id: uuid.UUID | None,
    unit_cost: Decimal,
    quantity: int,
    created_at: datetime,
) -> InventoryCostLayer:
    layer = InventoryCostLayer(
        organization_id=organization_id,
        product_id=product_id,
        source_type=source_type,
        source_id=source_id,
        unit_cost=money(unit_cost),
        quantity_received=quantity,
        quantity_remaining=quantity,
        created_at=created_at,
    )
    db.add(layer)
    await db.flush()
    return layer


async def consume_fifo(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity_needed: int,
    fallback_unit_cost: Decimal,
) -> Decimal:
    """Draws `quantity_needed` units oldest-layer-first and returns the total
    cost drawn. If layers run out (e.g. stock predating FIFO adoption, or a
    product whose current_stock was set directly rather than through a
    purchase), the remainder is costed at `fallback_unit_cost` — the
    product's own standing cost_price — so COGS is always a real number,
    never a crash, for data that was never given a cost layer."""
    result = await db.execute(
        select(InventoryCostLayer)
        .where(
            InventoryCostLayer.organization_id == organization_id,
            InventoryCostLayer.product_id == product_id,
            InventoryCostLayer.quantity_remaining > 0,
        )
        .order_by(InventoryCostLayer.created_at, InventoryCostLayer.id)
        .with_for_update()
    )
    layers = list(result.scalars())

    remaining = quantity_needed
    total_cost = Decimal("0")
    for layer in layers:
        if remaining <= 0:
            break
        take = min(layer.quantity_remaining, remaining)
        layer.quantity_remaining -= take
        total_cost += layer.unit_cost * take
        remaining -= take

    if remaining > 0:
        total_cost += money(fallback_unit_cost) * remaining

    return money(total_cost)


async def reduce_layer_for_source(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    product_id: uuid.UUID,
    source_type: CostLayerSource,
    source_id: uuid.UUID,
    quantity: int,
) -> None:
    """Voiding/returning a purchase reverses the specific layer that
    purchase created (clamped at 0 — if it was already partly consumed by a
    sale, that consumption stays real; we just can't un-consume it here)."""
    result = await db.execute(
        select(InventoryCostLayer).where(
            InventoryCostLayer.organization_id == organization_id,
            InventoryCostLayer.product_id == product_id,
            InventoryCostLayer.source_type == source_type,
            InventoryCostLayer.source_id == source_id,
        )
        .with_for_update()
    )
    layer = result.scalar_one_or_none()
    if layer is None:
        return
    layer.quantity_remaining = max(0, layer.quantity_remaining - quantity)

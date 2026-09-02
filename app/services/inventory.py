import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.inventory import InventoryMovement, MovementType
from app.models.product import Product


async def adjust_stock(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity_delta: int,
    reason: str,
    performed_by: uuid.UUID,
) -> Product:
    """Manual stock correction (stock count reconciliation, damage, loss...).
    quantity_delta > 0 adds stock, < 0 removes it. Always ledgered."""
    if quantity_delta == 0:
        raise ValidationAppError("quantity_delta must not be zero", code="INVALID_ADJUSTMENT")

    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.organization_id == organization_id).with_for_update()
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise NotFoundError("Product not found")

    previous_quantity = product.current_stock
    new_quantity = previous_quantity + quantity_delta
    if new_quantity < 0:
        raise ValidationAppError(
            f"Adjustment would take stock negative (current: {previous_quantity}, delta: {quantity_delta})",
            code="INVALID_ADJUSTMENT",
        )

    product.current_stock = new_quantity
    movement_type = MovementType.ADJUSTMENT_IN if quantity_delta > 0 else MovementType.ADJUSTMENT_OUT

    db.add(
        InventoryMovement(
            organization_id=organization_id,
            product_id=product.id,
            movement_type=movement_type,
            quantity=quantity_delta,
            previous_quantity=previous_quantity,
            resulting_quantity=new_quantity,
            reference_type="manual_adjustment",
            reason=reason,
            performed_by=performed_by,
            created_at=datetime.now(timezone.utc),
        )
    )

    await db.flush()
    return product

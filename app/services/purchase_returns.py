import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.inventory import CostLayerSource, InventoryMovement, MovementType
from app.models.product import Product
from app.models.purchase import Purchase, PurchaseItem, PurchaseStatus
from app.models.return_models import PurchaseReturn, PurchaseReturnItem
from app.schemas.returns import PurchaseReturnCreate
from app.services.audit import log_action
from app.services.inventory_costing import reduce_layer_for_source
from app.services.money import money


async def _already_returned_quantity(db: AsyncSession, purchase_item_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.coalesce(func.sum(PurchaseReturnItem.quantity), 0)).where(
            PurchaseReturnItem.purchase_item_id == purchase_item_id
        )
    )
    return int(result.scalar_one())


async def create_purchase_return(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    purchase_id: uuid.UUID,
    payload: PurchaseReturnCreate,
    processed_by: uuid.UUID,
    request: Request | None = None,
) -> PurchaseReturn:
    result = await db.execute(
        select(Purchase)
        .where(Purchase.id == purchase_id, Purchase.organization_id == organization_id)
        .options(selectinload(Purchase.items))
        .with_for_update()
    )
    purchase = result.scalar_one_or_none()
    if purchase is None:
        raise NotFoundError("Purchase not found")
    if purchase.status != PurchaseStatus.COMPLETED:
        raise ValidationAppError("Only completed purchases can be returned against", code="INVALID_PURCHASE_STATUS")

    items_by_id: dict[uuid.UUID, PurchaseItem] = {item.id: item for item in purchase.items}
    now = datetime.now(timezone.utc)

    return_items: list[PurchaseReturnItem] = []
    movements: list[InventoryMovement] = []
    total_refund = Decimal("0")

    for line in payload.items:
        purchase_item = items_by_id.get(line.purchase_item_id)
        if purchase_item is None:
            raise NotFoundError(f"Purchase item {line.purchase_item_id} not found on this purchase")

        already_returned = await _already_returned_quantity(db, purchase_item.id)
        remaining = purchase_item.quantity - already_returned
        if line.quantity <= 0:
            raise ValidationAppError("Return quantity must be greater than zero", code="INVALID_QUANTITY")
        if line.quantity > remaining:
            raise ValidationAppError(
                f"Cannot return {line.quantity} of '{purchase_item.product_name}' — only {remaining} eligible",
                code="RETURN_EXCEEDS_PURCHASED_QUANTITY",
            )

        result = await db.execute(
            select(Product).where(Product.id == purchase_item.product_id, Product.organization_id == organization_id).with_for_update()
        )
        product = result.scalar_one_or_none()
        if product is None:
            raise NotFoundError(f"Product {purchase_item.product_id} not found")
        if product.current_stock < line.quantity:
            raise ValidationAppError(
                f"Cannot return {line.quantity} of '{product.name}' — only {product.current_stock} currently in stock (some may have already been sold)",
                code="STOCK_ALREADY_CONSUMED",
            )

        line_refund_amount = money(purchase_item.unit_cost_price * line.quantity)
        total_refund += line_refund_amount

        previous_quantity = product.current_stock
        product.current_stock -= line.quantity

        return_items.append(
            PurchaseReturnItem(
                purchase_item_id=purchase_item.id,
                product_id=product.id,
                quantity=line.quantity,
                line_refund_amount=line_refund_amount,
            )
        )
        movements.append(
            InventoryMovement(
                organization_id=organization_id,
                product_id=product.id,
                movement_type=MovementType.PURCHASE_RETURN,
                quantity=-line.quantity,
                previous_quantity=previous_quantity,
                resulting_quantity=product.current_stock,
                reference_type="purchase_return",
                reason=payload.reason,
                performed_by=processed_by,
                created_at=now,
            )
        )
        await reduce_layer_for_source(
            db,
            organization_id=organization_id,
            product_id=product.id,
            source_type=CostLayerSource.PURCHASE,
            source_id=purchase_item.id,
            quantity=line.quantity,
        )

    total_refund = money(total_refund)

    purchase_return = PurchaseReturn(
        organization_id=organization_id,
        purchase_id=purchase.id,
        processed_by=processed_by,
        reason=payload.reason,
        refund_amount=total_refund,
        created_at=now,
        items=return_items,
    )
    db.add(purchase_return)
    await db.flush()

    for movement in movements:
        movement.reference_id = purchase_return.id
        db.add(movement)

    await log_action(
        db,
        actor_user_id=processed_by,
        organization_id=organization_id,
        action="PURCHASE_RETURN_CREATED",
        resource_type="purchase_return",
        resource_id=str(purchase_return.id),
        reason=payload.reason,
        metadata={"purchase_id": str(purchase.id), "refund_amount": str(total_refund)},
        request=request,
    )

    await db.flush()
    result = await db.execute(
        select(PurchaseReturn).where(PurchaseReturn.id == purchase_return.id).options(selectinload(PurchaseReturn.items))
    )
    return result.scalar_one()

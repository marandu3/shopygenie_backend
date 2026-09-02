import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.inventory import CostLayerSource, InventoryMovement, MovementType
from app.models.product import Product
from app.models.purchase import Purchase, PurchaseItem, PurchaseStatus
from app.schemas.purchase import PurchaseCreate
from app.services.audit import log_action
from app.services.inventory_costing import add_cost_layer, reduce_layer_for_source
from app.services.money import money
from app.services.numbering import next_document_number


async def create_purchase(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    purchased_by: uuid.UUID,
    payload: PurchaseCreate,
    request: Request | None = None,
) -> Purchase:
    product_ids = sorted({item.product_id for item in payload.items}, key=str)
    products_by_id: dict[uuid.UUID, Product] = {}
    for pid in product_ids:
        result = await db.execute(
            select(Product).where(Product.id == pid, Product.organization_id == organization_id).with_for_update()
        )
        product = result.scalar_one_or_none()
        if product is None:
            raise NotFoundError(f"Product {pid} not found")
        products_by_id[pid] = product

    now = datetime.now(timezone.utc)
    total_amount = Decimal("0")
    purchase_items: list[PurchaseItem] = []
    movements: list[InventoryMovement] = []

    for item in payload.items:
        product = products_by_id[item.product_id]
        unit_cost_price = money(item.unit_cost_price)
        line_total = money(unit_cost_price * item.quantity)

        previous_quantity = product.current_stock
        product.current_stock += item.quantity
        # Last-cost valuation: the most recent purchase price becomes the
        # product's standing cost price (used for future COGS/valuation).
        product.cost_price = unit_cost_price

        purchase_items.append(
            PurchaseItem(
                product_id=product.id,
                product_name=product.name,
                quantity=item.quantity,
                unit_cost_price=unit_cost_price,
                line_total=line_total,
            )
        )
        movements.append(
            InventoryMovement(
                organization_id=organization_id,
                product_id=product.id,
                movement_type=MovementType.PURCHASE,
                quantity=item.quantity,
                previous_quantity=previous_quantity,
                resulting_quantity=product.current_stock,
                reference_type="purchase",
                performed_by=purchased_by,
                created_at=now,
            )
        )
        total_amount += line_total

    purchase_number = await next_document_number(db, organization_id, "PURCHASE")

    purchase = Purchase(
        organization_id=organization_id,
        branch_id=payload.branch_id,
        supplier_id=payload.supplier_id,
        purchased_by=purchased_by,
        purchase_number=purchase_number,
        total_amount=total_amount,
        status=PurchaseStatus.COMPLETED,
        items=purchase_items,
    )
    db.add(purchase)
    await db.flush()  # assigns purchase.id and each purchase_item.id

    for movement in movements:
        movement.reference_id = purchase.id
        db.add(movement)

    for purchase_item in purchase_items:
        await add_cost_layer(
            db,
            organization_id=organization_id,
            product_id=purchase_item.product_id,
            source_type=CostLayerSource.PURCHASE,
            source_id=purchase_item.id,
            unit_cost=purchase_item.unit_cost_price,
            quantity=purchase_item.quantity,
            created_at=now,
        )

    await log_action(
        db,
        actor_user_id=purchased_by,
        organization_id=organization_id,
        action="PURCHASE_CREATED",
        resource_type="purchase",
        resource_id=str(purchase.id),
        metadata={"purchase_number": purchase_number, "total_amount": str(total_amount)},
        request=request,
    )

    await db.flush()
    result = await db.execute(
        select(Purchase).where(Purchase.id == purchase.id).options(selectinload(Purchase.items))
    )
    return result.scalar_one()


async def void_purchase(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    purchase_id: uuid.UUID,
    voided_by: uuid.UUID,
    reason: str,
    request: Request | None = None,
) -> Purchase:
    result = await db.execute(
        select(Purchase)
        .where(Purchase.id == purchase_id, Purchase.organization_id == organization_id)
        .options(selectinload(Purchase.items))
        .with_for_update()
    )
    purchase = result.scalar_one_or_none()
    if purchase is None:
        raise NotFoundError("Purchase not found")
    if purchase.status == PurchaseStatus.VOIDED:
        raise ValidationAppError("Purchase is already voided", code="ALREADY_VOIDED")

    now = datetime.now(timezone.utc)
    for item in purchase.items:
        product = await db.get(Product, item.product_id)
        if product is not None:
            if product.current_stock < item.quantity:
                raise ValidationAppError(
                    f"Cannot void: '{product.name}' stock has already been partially sold below the purchased quantity",
                    code="STOCK_ALREADY_CONSUMED",
                )
            previous_quantity = product.current_stock
            product.current_stock -= item.quantity
            db.add(
                InventoryMovement(
                    organization_id=organization_id,
                    product_id=product.id,
                    movement_type=MovementType.PURCHASE_RETURN,
                    quantity=-item.quantity,
                    previous_quantity=previous_quantity,
                    resulting_quantity=product.current_stock,
                    reference_type="purchase_void",
                    reference_id=purchase.id,
                    reason=reason,
                    performed_by=voided_by,
                    created_at=now,
                )
            )
            await reduce_layer_for_source(
                db,
                organization_id=organization_id,
                product_id=product.id,
                source_type=CostLayerSource.PURCHASE,
                source_id=item.id,
                quantity=item.quantity,
            )

    purchase.status = PurchaseStatus.VOIDED
    purchase.void_reason = reason
    purchase.voided_by = voided_by
    purchase.voided_at = now

    await log_action(
        db,
        actor_user_id=voided_by,
        organization_id=organization_id,
        action="PURCHASE_VOIDED",
        resource_type="purchase",
        resource_id=str(purchase.id),
        reason=reason,
        request=request,
    )

    await db.flush()
    return purchase

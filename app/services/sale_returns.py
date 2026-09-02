import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.debt import Debt
from app.models.inventory import InventoryMovement, MovementType
from app.models.product import Product
from app.models.return_models import SaleReturn, SaleReturnItem
from app.models.sale import Sale, SaleItem, SaleStatus
from app.schemas.returns import SaleReturnCreate
from app.services.audit import log_action
from app.services.money import money


async def _already_returned_quantity(db: AsyncSession, sale_item_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.coalesce(func.sum(SaleReturnItem.quantity), 0)).where(SaleReturnItem.sale_item_id == sale_item_id)
    )
    return int(result.scalar_one())


async def create_sale_return(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    sale_id: uuid.UUID,
    payload: SaleReturnCreate,
    processed_by: uuid.UUID,
    request: Request | None = None,
) -> SaleReturn:
    result = await db.execute(
        select(Sale)
        .where(Sale.id == sale_id, Sale.organization_id == organization_id)
        .options(selectinload(Sale.items))
        .with_for_update()
    )
    sale = result.scalar_one_or_none()
    if sale is None:
        raise NotFoundError("Sale not found")
    if sale.status != SaleStatus.COMPLETED:
        raise ValidationAppError("Only completed sales can be returned against", code="INVALID_SALE_STATUS")

    items_by_id = {item.id: item for item in sale.items}
    now = datetime.now(timezone.utc)

    return_items: list[SaleReturnItem] = []
    movements: list[InventoryMovement] = []
    total_refund = Decimal("0")

    for line in payload.items:
        sale_item = items_by_id.get(line.sale_item_id)
        if sale_item is None:
            raise NotFoundError(f"Sale item {line.sale_item_id} not found on this sale")

        already_returned = await _already_returned_quantity(db, sale_item.id)
        remaining = sale_item.quantity - already_returned
        if line.quantity <= 0:
            raise ValidationAppError("Return quantity must be greater than zero", code="INVALID_QUANTITY")
        if line.quantity > remaining:
            raise ValidationAppError(
                f"Cannot return {line.quantity} of '{sale_item.product_name}' — only {remaining} eligible (already returned: {already_returned})",
                code="RETURN_EXCEEDS_SOLD_QUANTITY",
            )

        result = await db.execute(
            select(Product).where(Product.id == sale_item.product_id, Product.organization_id == organization_id).with_for_update()
        )
        product = result.scalar_one_or_none()
        if product is None:
            raise NotFoundError(f"Product {sale_item.product_id} not found")

        # Proportional refund using the ORIGINAL effective per-unit price
        # (after that line's own discount), not the list price.
        effective_unit_price = sale_item.line_total / sale_item.quantity
        line_refund_amount = money(effective_unit_price * line.quantity)
        total_refund += line_refund_amount

        previous_quantity = product.current_stock
        product.current_stock += line.quantity

        return_items.append(
            SaleReturnItem(
                sale_item_id=sale_item.id,
                product_id=product.id,
                quantity=line.quantity,
                line_refund_amount=line_refund_amount,
            )
        )
        movements.append(
            InventoryMovement(
                organization_id=organization_id,
                product_id=product.id,
                movement_type=MovementType.SALE_RETURN,
                quantity=line.quantity,
                previous_quantity=previous_quantity,
                resulting_quantity=product.current_stock,
                reference_type="sale_return",
                reason=payload.reason,
                performed_by=processed_by,
                created_at=now,
            )
        )

    total_refund = money(total_refund)

    # Apply the refund to any open receivable from this exact sale first —
    # a return reduces what the customer still owes, it never changes the
    # immutable original `amount` on the Debt (see app/models/debt.py).
    debt_reduction = Decimal("0")
    debt_result = await db.execute(
        select(Debt).where(Debt.sale_id == sale.id, Debt.organization_id == organization_id, Debt.cleared.is_(False)).with_for_update()
    )
    debt = debt_result.scalar_one_or_none()
    if debt is not None:
        debt_reduction = min(total_refund, debt.balance)
        debt.balance = money(debt.balance - debt_reduction)
        debt.cleared = debt.balance == 0

    cash_refund_due = money(total_refund - debt_reduction)

    sale_return = SaleReturn(
        organization_id=organization_id,
        sale_id=sale.id,
        processed_by=processed_by,
        reason=payload.reason,
        refund_amount=total_refund,
        debt_reduction=debt_reduction,
        cash_refund_due=cash_refund_due,
        created_at=now,
        items=return_items,
    )
    db.add(sale_return)
    await db.flush()

    for movement in movements:
        movement.reference_id = sale_return.id
        db.add(movement)

    await log_action(
        db,
        actor_user_id=processed_by,
        organization_id=organization_id,
        action="SALE_RETURN_CREATED",
        resource_type="sale_return",
        resource_id=str(sale_return.id),
        reason=payload.reason,
        metadata={"sale_id": str(sale.id), "refund_amount": str(total_refund), "cash_refund_due": str(cash_refund_due)},
        request=request,
    )

    await db.flush()
    result = await db.execute(select(SaleReturn).where(SaleReturn.id == sale_return.id).options(selectinload(SaleReturn.items)))
    return result.scalar_one()

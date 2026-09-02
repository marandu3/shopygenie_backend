import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import InsufficientStockError, NotFoundError, ValidationAppError
from app.models.customer import Customer
from app.models.debt import Debt
from app.models.inventory import InventoryMovement, MovementType
from app.models.organization import Organization
from app.models.product import Product
from app.models.sale import Payment, PaymentMethod, Sale, SaleItem, SaleStatus
from app.schemas.sale import SaleCreate
from app.services.audit import log_action
from app.services.money import money, percent_of
from app.services.numbering import next_document_number


async def create_sale(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    cashier_id: uuid.UUID,
    payload: SaleCreate,
    request: Request | None = None,
) -> Sale:
    org = await db.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Organization not found")

    customer = None
    if payload.customer_id is not None:
        customer = await db.get(Customer, payload.customer_id)
        if customer is None or customer.organization_id != organization_id:
            raise NotFoundError("Customer not found")

    # --- Lock every product row up front (consistent order = product_id) to
    # avoid deadlocks between concurrent sales sharing overlapping products,
    # and to prevent two cashiers from overselling the same last unit. ---
    product_ids = sorted({item.product_id for item in payload.items}, key=str)
    products_by_id: dict[uuid.UUID, Product] = {}
    for pid in product_ids:
        result = await db.execute(
            select(Product).where(Product.id == pid, Product.organization_id == organization_id).with_for_update()
        )
        product = result.scalar_one_or_none()
        if product is None:
            raise NotFoundError(f"Product {pid} not found")
        if not product.is_active:
            raise ValidationAppError(f"Product '{product.name}' is not active", code="PRODUCT_INACTIVE")
        products_by_id[pid] = product

    subtotal = Decimal("0")
    discount_total = Decimal("0")
    sale_items: list[SaleItem] = []
    movements: list[InventoryMovement] = []
    now = datetime.now(timezone.utc)

    for item in payload.items:
        product = products_by_id[item.product_id]

        if product.current_stock < item.quantity:
            raise InsufficientStockError(product.name, product.current_stock, item.quantity)

        line_subtotal = money(Decimal(product.selling_price) * item.quantity)
        discount_amount = money(item.discount_amount)
        if discount_amount > line_subtotal:
            raise ValidationAppError(
                f"Discount ({discount_amount}) cannot exceed line subtotal ({line_subtotal}) for '{product.name}'",
                code="INVALID_DISCOUNT",
            )
        line_total = money(line_subtotal - discount_amount)  # never negative — guaranteed by the check above

        previous_quantity = product.current_stock
        product.current_stock -= item.quantity

        sale_items.append(
            SaleItem(
                product_id=product.id,
                product_name=product.name,
                unit_selling_price=product.selling_price,
                unit_cost_price=product.cost_price,
                quantity=item.quantity,
                discount_amount=discount_amount,
                line_total=line_total,
            )
        )
        movements.append(
            InventoryMovement(
                organization_id=organization_id,
                product_id=product.id,
                movement_type=MovementType.SALE,
                quantity=-item.quantity,
                previous_quantity=previous_quantity,
                resulting_quantity=product.current_stock,
                reference_type="sale",
                performed_by=cashier_id,
                created_at=now,
            )
        )

        subtotal += line_subtotal
        discount_total += discount_amount

    net_before_tax = money(subtotal - discount_total)
    tax_rate = Decimal(str(org.tax_rate_percent))

    if org.tax_inclusive_pricing:
        tax_total = money(net_before_tax - (net_before_tax / (1 + tax_rate / 100)))
        total_amount = net_before_tax
    else:
        tax_total = percent_of(net_before_tax, tax_rate)
        total_amount = money(net_before_tax + tax_total)

    sale_number = await next_document_number(db, organization_id, "SALE")

    sale = Sale(
        organization_id=organization_id,
        branch_id=payload.branch_id,
        register_id=payload.register_id,
        customer_id=payload.customer_id,
        cashier_id=cashier_id,
        sale_number=sale_number,
        subtotal=subtotal,
        discount_total=discount_total,
        tax_total=tax_total,
        total_amount=total_amount,
        status=SaleStatus.COMPLETED,
        items=sale_items,
    )
    db.add(sale)
    await db.flush()  # assign sale.id for movement/payment references

    for movement in movements:
        movement.reference_id = sale.id
        db.add(movement)

    paid_total = Decimal("0")
    payments: list[Payment] = []
    for p in payload.payments:
        try:
            method = PaymentMethod(p.method)
        except ValueError:
            raise ValidationAppError(f"Unknown payment method: {p.method}", code="INVALID_PAYMENT_METHOD")
        amount = money(p.amount)
        paid_total += amount
        payments.append(
            Payment(
                organization_id=organization_id,
                sale_id=sale.id,
                customer_id=payload.customer_id,
                received_by=cashier_id,
                amount=amount,
                method=method,
                reference=p.reference,
                created_at=now,
            )
        )

    if paid_total > total_amount:
        raise ValidationAppError("Total payments cannot exceed the sale total", code="OVERPAYMENT")

    remainder = money(total_amount - paid_total)
    if remainder > 0:
        if not payload.allow_credit or payload.customer_id is None:
            raise ValidationAppError(
                "Payments do not cover the full total. Set allow_credit=true with a customer to sell on credit.",
                code="INCOMPLETE_PAYMENT",
            )
        db.add(
            Debt(
                organization_id=organization_id,
                customer_id=payload.customer_id,
                sale_id=sale.id,
                amount=remainder,
                balance=remainder,
                cleared=False,
                created_at=now,
            )
        )

    for payment in payments:
        db.add(payment)

    await log_action(
        db,
        actor_user_id=cashier_id,
        organization_id=organization_id,
        action="SALE_CREATED",
        resource_type="sale",
        resource_id=str(sale.id),
        metadata={"sale_number": sale_number, "total_amount": str(total_amount)},
        request=request,
    )

    await db.flush()

    result = await db.execute(
        select(Sale)
        .where(Sale.id == sale.id)
        .options(selectinload(Sale.items), selectinload(Sale.payments))
    )
    return result.scalar_one()


async def void_sale(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    sale_id: uuid.UUID,
    voided_by: uuid.UUID,
    reason: str,
    request: Request | None = None,
) -> Sale:
    """Voiding never deletes the row — it flips status and reverses stock via
    a new ledger entry, keeping full history (MASTER PROMPT §27, §61)."""
    result = await db.execute(
        select(Sale)
        .where(Sale.id == sale_id, Sale.organization_id == organization_id)
        .options(selectinload(Sale.items), selectinload(Sale.payments))
        .with_for_update()
    )
    sale = result.scalar_one_or_none()
    if sale is None:
        raise NotFoundError("Sale not found")
    if sale.status == SaleStatus.VOIDED:
        raise ValidationAppError("Sale is already voided", code="ALREADY_VOIDED")

    now = datetime.now(timezone.utc)
    for item in sale.items:
        product = await db.get(Product, item.product_id)
        if product is not None:
            previous_quantity = product.current_stock
            product.current_stock += item.quantity
            db.add(
                InventoryMovement(
                    organization_id=organization_id,
                    product_id=product.id,
                    movement_type=MovementType.SALE_RETURN,
                    quantity=item.quantity,
                    previous_quantity=previous_quantity,
                    resulting_quantity=product.current_stock,
                    reference_type="sale_void",
                    reference_id=sale.id,
                    reason=reason,
                    performed_by=voided_by,
                    created_at=now,
                )
            )

    sale.status = SaleStatus.VOIDED
    sale.void_reason = reason
    sale.voided_by = voided_by
    sale.voided_at = now

    # Any receivable this sale created is no longer collectible.
    debt_result = await db.execute(
        select(Debt).where(Debt.sale_id == sale.id, Debt.organization_id == organization_id)
    )
    for debt in debt_result.scalars():
        debt.balance = Decimal("0")
        debt.cleared = True

    await log_action(
        db,
        actor_user_id=voided_by,
        organization_id=organization_id,
        action="SALE_VOIDED",
        resource_type="sale",
        resource_id=str(sale.id),
        reason=reason,
        request=request,
    )

    await db.flush()
    return sale

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, require_permission, require_tenant_context
from app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.core.permissions import PRODUCTS_CREATE, PRODUCTS_DELETE, PRODUCTS_UPDATE, PRODUCTS_VIEW
from app.db.session import get_db
from app.models.inventory import InventoryMovement, MovementType
from app.models.product import Product
from app.schemas.common import MessageResponse
from app.schemas.inventory import InventoryMovementOut
from app.schemas.product import (
    InventoryAdjustmentRequest,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    StockLevelOut,
    StockValuationLine,
    StockValuationOut,
)
from app.services.inventory import adjust_stock

router = APIRouter(prefix="/products", tags=["Products"])


@router.post("", response_model=ProductOut, status_code=201)
async def create_product(
    payload: ProductCreate,
    ctx: AuthContext = Depends(require_permission(PRODUCTS_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    product = Product(organization_id=org_id, **payload.model_dump())
    db.add(product)
    await db.flush()

    if product.current_stock > 0:
        # Every unit of stock must be traceable to a ledger entry — an
        # opening balance is the entry for stock that existed before the
        # product had any purchases/sales (fixes: current_stock as the only
        # source of truth, and keeps /reconciliation/inventory meaningful).
        db.add(
            InventoryMovement(
                organization_id=org_id,
                product_id=product.id,
                movement_type=MovementType.OPENING_BALANCE,
                quantity=product.current_stock,
                previous_quantity=0,
                resulting_quantity=product.current_stock,
                reference_type="product_created",
                performed_by=ctx.user_id,
                created_at=datetime.now(timezone.utc),
            )
        )

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("A product with this SKU or barcode already exists")
    await db.refresh(product)
    return product


@router.get("", response_model=list[ProductOut])
async def list_products(
    ctx: AuthContext = Depends(require_permission(PRODUCTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    result = await db.execute(select(Product).where(Product.organization_id == org_id).order_by(Product.name))
    return list(result.scalars())


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission(PRODUCTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != org_id:
        raise NotFoundError("Product not found")
    return product


@router.put("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    ctx: AuthContext = Depends(require_permission(PRODUCTS_UPDATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != org_id:
        raise NotFoundError("Product not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("A product with this SKU or barcode already exists")
    await db.refresh(product)
    return product


@router.delete("/{product_id}", response_model=MessageResponse)
async def deactivate_product(
    product_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission(PRODUCTS_DELETE)),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete only — products are referenced by historical sale/purchase
    line items and must never be hard-deleted (MASTER PROMPT §61)."""
    org_id = ctx.require_organization_id()
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != org_id:
        raise NotFoundError("Product not found")

    product.is_active = False
    await db.commit()
    return MessageResponse(detail="Product deactivated")


@router.post("/{product_id}/adjust-stock", response_model=ProductOut)
async def adjust_product_stock(
    product_id: uuid.UUID,
    payload: InventoryAdjustmentRequest,
    ctx: AuthContext = Depends(require_permission(PRODUCTS_UPDATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    product = await adjust_stock(
        db,
        organization_id=org_id,
        product_id=product_id,
        quantity_delta=payload.quantity_delta,
        reason=payload.reason,
        performed_by=ctx.user_id,
    )
    await db.commit()
    await db.refresh(product)
    return product


@router.get("/{product_id}/movements", response_model=list[InventoryMovementOut])
async def product_movements(
    product_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission(PRODUCTS_VIEW)),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    org_id = ctx.require_organization_id()
    product = await db.get(Product, product_id)
    if product is None or product.organization_id != org_id:
        raise NotFoundError("Product not found")

    result = await db.execute(
        select(InventoryMovement)
        .where(InventoryMovement.organization_id == org_id, InventoryMovement.product_id == product_id)
        .order_by(InventoryMovement.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


@router.get("/stock/levels", response_model=list[StockLevelOut])
async def stock_levels(
    ctx: AuthContext = Depends(require_permission(PRODUCTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    result = await db.execute(
        select(Product.id, Product.name, Product.current_stock, Product.low_stock_alert).where(
            Product.organization_id == org_id, Product.is_active.is_(True)
        )
    )
    return [StockLevelOut(id=r.id, name=r.name, current_stock=r.current_stock, low_stock_alert=r.low_stock_alert) for r in result.all()]


@router.get("/stock/low", response_model=list[StockLevelOut])
async def low_stock_products(
    ctx: AuthContext = Depends(require_permission(PRODUCTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    result = await db.execute(
        select(Product.id, Product.name, Product.current_stock, Product.low_stock_alert).where(
            Product.organization_id == org_id,
            Product.is_active.is_(True),
            Product.low_stock_alert.is_not(None),
            Product.current_stock < Product.low_stock_alert,
        )
    )
    return [StockLevelOut(id=r.id, name=r.name, current_stock=r.current_stock, low_stock_alert=r.low_stock_alert) for r in result.all()]


@router.get("/stock/valuation", response_model=StockValuationOut)
async def stock_valuation(
    ctx: AuthContext = Depends(require_permission(PRODUCTS_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    result = await db.execute(
        select(Product.id, Product.name, Product.current_stock, Product.cost_price).where(
            Product.organization_id == org_id, Product.is_active.is_(True)
        )
    )
    lines = []
    total = 0
    for r in result.all():
        valuation = float(r.current_stock) * float(r.cost_price)
        total += valuation
        lines.append(StockValuationLine(id=r.id, name=r.name, current_stock=r.current_stock, cost_price=float(r.cost_price), valuation=valuation))
    return StockValuationOut(total_valuation=total, lines=lines)

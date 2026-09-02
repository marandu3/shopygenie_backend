import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import AuthContext, require_permission
from app.core.exceptions import NotFoundError
from app.core.permissions import PURCHASES_CREATE, PURCHASES_RETURN, PURCHASES_VIEW
from app.db.session import get_db
from app.models.purchase import Purchase
from app.schemas.purchase import PurchaseCreate, PurchaseOut, VoidPurchaseRequest
from app.schemas.returns import PurchaseReturnCreate, PurchaseReturnOut
from app.services.purchase_returns import create_purchase_return
from app.services.purchases import create_purchase, void_purchase

router = APIRouter(prefix="/purchases", tags=["Purchases"])


@router.post("", response_model=PurchaseOut, status_code=201)
async def create_purchase_endpoint(
    payload: PurchaseCreate,
    request: Request,
    ctx: AuthContext = Depends(require_permission(PURCHASES_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    purchase = await create_purchase(db, organization_id=org_id, purchased_by=ctx.user_id, payload=payload, request=request)
    await db.commit()
    await db.refresh(purchase, attribute_names=["items"])
    return purchase


@router.post("/{purchase_id}/returns", response_model=PurchaseReturnOut, status_code=201)
async def create_purchase_return_endpoint(
    purchase_id: uuid.UUID,
    payload: PurchaseReturnCreate,
    request: Request,
    ctx: AuthContext = Depends(require_permission(PURCHASES_RETURN)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    purchase_return = await create_purchase_return(
        db, organization_id=org_id, purchase_id=purchase_id, payload=payload, processed_by=ctx.user_id, request=request
    )
    await db.commit()
    await db.refresh(purchase_return, attribute_names=["items"])
    return purchase_return


@router.get("", response_model=list[PurchaseOut])
async def list_purchases(
    ctx: AuthContext = Depends(require_permission(PURCHASES_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    result = await db.execute(
        select(Purchase)
        .where(Purchase.organization_id == org_id)
        .options(selectinload(Purchase.items))
        .order_by(Purchase.created_at.desc())
    )
    return list(result.scalars())


@router.get("/{purchase_id}", response_model=PurchaseOut)
async def get_purchase(
    purchase_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission(PURCHASES_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    result = await db.execute(
        select(Purchase)
        .where(Purchase.id == purchase_id, Purchase.organization_id == org_id)
        .options(selectinload(Purchase.items))
    )
    purchase = result.scalar_one_or_none()
    if purchase is None:
        raise NotFoundError("Purchase not found")
    return purchase


@router.post("/{purchase_id}/void", response_model=PurchaseOut)
async def void_purchase_endpoint(
    purchase_id: uuid.UUID,
    payload: VoidPurchaseRequest,
    request: Request,
    ctx: AuthContext = Depends(require_permission(PURCHASES_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    purchase = await void_purchase(
        db, organization_id=org_id, purchase_id=purchase_id, voided_by=ctx.user_id, reason=payload.reason, request=request
    )
    await db.commit()
    await db.refresh(purchase, attribute_names=["items"])
    return purchase

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import AuthContext, require_permission
from app.core.exceptions import NotFoundError
from app.core.permissions import SALES_CREATE, SALES_REFUND, SALES_VIEW, SALES_VOID
from app.db.session import get_db
from app.models.sale import Sale
from app.schemas.returns import SaleReturnCreate, SaleReturnOut
from app.schemas.sale import SaleCreate, SaleOut, VoidSaleRequest
from app.services.sale_returns import create_sale_return
from app.services.sales import create_sale, void_sale

router = APIRouter(prefix="/sales", tags=["Sales"])


@router.post("", response_model=SaleOut, status_code=201)
async def create_sale_endpoint(
    payload: SaleCreate,
    request: Request,
    ctx: AuthContext = Depends(require_permission(SALES_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    sale = await create_sale(db, organization_id=org_id, cashier_id=ctx.user_id, payload=payload, request=request)
    await db.commit()
    await db.refresh(sale, attribute_names=["items", "payments"])
    return sale


@router.post("/{sale_id}/returns", response_model=SaleReturnOut, status_code=201)
async def create_sale_return_endpoint(
    sale_id: uuid.UUID,
    payload: SaleReturnCreate,
    request: Request,
    ctx: AuthContext = Depends(require_permission(SALES_REFUND)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    sale_return = await create_sale_return(
        db, organization_id=org_id, sale_id=sale_id, payload=payload, processed_by=ctx.user_id, request=request
    )
    await db.commit()
    await db.refresh(sale_return, attribute_names=["items"])
    return sale_return


@router.get("", response_model=list[SaleOut])
async def list_sales(
    ctx: AuthContext = Depends(require_permission(SALES_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    result = await db.execute(
        select(Sale)
        .where(Sale.organization_id == org_id)
        .options(selectinload(Sale.items), selectinload(Sale.payments))
        .order_by(Sale.created_at.desc())
    )
    return list(result.scalars())


@router.get("/{sale_id}", response_model=SaleOut)
async def get_sale(
    sale_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission(SALES_VIEW)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    result = await db.execute(
        select(Sale)
        .where(Sale.id == sale_id, Sale.organization_id == org_id)
        .options(selectinload(Sale.items), selectinload(Sale.payments))
    )
    sale = result.scalar_one_or_none()
    if sale is None:
        raise NotFoundError("Sale not found")
    return sale


@router.post("/{sale_id}/void", response_model=SaleOut)
async def void_sale_endpoint(
    sale_id: uuid.UUID,
    payload: VoidSaleRequest,
    request: Request,
    ctx: AuthContext = Depends(require_permission(SALES_VOID)),
    db: AsyncSession = Depends(get_db),
):
    org_id = ctx.require_organization_id()
    sale = await void_sale(
        db, organization_id=org_id, sale_id=sale_id, voided_by=ctx.user_id, reason=payload.reason, request=request
    )
    await db.commit()
    await db.refresh(sale, attribute_names=["items", "payments"])
    return sale
